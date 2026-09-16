"""Auditoría de chunking (Nucleoeléctrica, real): el membrete "NUCLEOELECTRICA
ARGENTINA S.A. HOJA DE ESPECIFICACIONES TÉCNICAS DE COMPRA" se repite en casi
todas las páginas de un anexo de 22, pero Document Intelligence lo marca de
forma INCONSISTENTE: la mayoría de las veces viene como comentario
`<!-- PageHeader="..." -->` (que ya se descarta sin más), pero en unas pocas
páginas ese mismo texto sale como heading real (`#`/`##`). Como
`_detect_repeated_heading_boilerplate` decide por frecuencia y la mayoría de
las repeticiones quedan invisibles (se tiran como comentario antes de llegar
a heading), nunca cruza el umbral y el membrete termina como ancestro de
varios chunks.

Fix: `_parse_markdown_blocks` ahora hace una pasada previa sobre TODO el
markdown para juntar el texto de cualquier comentario `PageHeader`/`PageFooter`
-- es la propia Document Intelligence confirmando, en otra página del mismo
documento, que ese texto es membrete. Cualquier heading que matchee ese texto
se marca `is_confirmed_page_furniture`, y `_detect_repeated_heading_boilerplate`
lo incluye en el set a descartar SIN depender de frecuencia.

Además, el numerador de página ("HOJA 1 de 22", "HOJA 2 de 22"...) tiene el
mismo problema pero por otro motivo: el texto cambia en cada página, así que
ni siquiera el dedup por texto EXACTO repetido (`_drop_repeated_page_furniture`)
lo agarra. Fix: `_drop_page_counters` reconoce el patrón "Hoja/Página N de/​/ M"
sin importar el número -- convención genérica de plantillas institucionales,
no vocabulario de un pliego puntual.
"""

from __future__ import annotations

from indexing.chunking.block_merging import _to_intermediate_blocks
from indexing.chunking.headings import _detect_repeated_heading_boilerplate
from indexing.chunking.page_furniture import _drop_page_counters
from indexing.document_intelligence.markdown_parsing import (
    _collect_page_header_footer_texts,
    _parse_markdown_blocks,
)

MEMBRETE = "NUCLEOELECTRICA ARGENTINA S.A. HOJA DE ESPECIFICACIONES TÉCNICAS DE COMPRA"


def _markdown_con_membrete_inconsistente() -> str:
    """Reproduce la forma real: 20 páginas, el membrete viene como comentario
    `PageHeader` en 18 de ellas, y como heading real (`##`) en solo 2 -- muy
    por debajo del umbral de frecuencia (50%) que usa
    `_detect_repeated_heading_boilerplate` por sí sola."""
    partes = []
    for pagina in range(1, 21):
        if pagina in (1, 15):
            partes.append(f'## {MEMBRETE}')
        else:
            partes.append(f'<!-- PageHeader="{MEMBRETE}" -->')
        partes.append(f"HOJA\n{pagina} de 20")
        partes.append(f"Artículo {pagina}. Contenido sustantivo y distinto de la página {pagina}.")
        partes.append("<!-- PageBreak -->")
    return "\n\n".join(partes)


# ---------------------------------------------------------------------------
# `_collect_page_header_footer_texts` / `is_confirmed_page_furniture`
# ---------------------------------------------------------------------------


def test_collect_page_header_footer_texts_junta_el_texto_normalizado() -> None:
    markdown = (
        '<!-- PageHeader="Banco de la Provincia" -->\n'
        '<!-- PageFooter="Firma y Aclaración" -->\n'
        "Cuerpo real de la página."
    )

    textos = _collect_page_header_footer_texts(markdown)

    assert textos == {"banco de la provincia", "firma y aclaración"}


def test_heading_que_coincide_con_un_pageheader_previo_queda_marcado() -> None:
    markdown = (
        f'<!-- PageHeader="{MEMBRETE}" -->\n'
        "Contenido de la página 1.\n\n"
        "<!-- PageBreak -->\n\n"
        f"## {MEMBRETE}\n\n"
        "Contenido de la página 2."
    )

    blocks, heading_levels_by_order, _table_positions = _parse_markdown_blocks(markdown)
    headings = [b for b in blocks if b["source_order"] in heading_levels_by_order]

    assert len(headings) == 1
    assert headings[0]["content"] == MEMBRETE
    assert headings[0]["is_confirmed_page_furniture"] is True


def test_heading_sin_pageheader_previo_no_se_marca() -> None:
    """Guarda: no cualquier heading repetido se marca -- solo el que coincide
    con un texto que DI confirmó como PageHeader/PageFooter en otra página."""
    markdown = "# ARTÍCULO 1: OBJETO\n\nContenido real."

    blocks, heading_levels_by_order, _table_positions = _parse_markdown_blocks(markdown)
    headings = [b for b in blocks if b["source_order"] in heading_levels_by_order]

    assert len(headings) == 1
    assert "is_confirmed_page_furniture" not in headings[0]


# ---------------------------------------------------------------------------
# `_detect_repeated_heading_boilerplate`: la señal confirmada no depende de frecuencia
# ---------------------------------------------------------------------------


def test_heading_confirmado_se_descarta_aunque_aparezca_una_sola_vez() -> None:
    blocks = [
        {
            "page_number": 1,
            "heading_level": 1,
            "content": MEMBRETE,
            "is_confirmed_page_furniture": True,
        },
        *[
            {"page_number": p, "heading_level": None, "content": f"Cuerpo página {p}."}
            for p in range(2, 12)
        ],
    ]

    boilerplate = _detect_repeated_heading_boilerplate(blocks)

    assert MEMBRETE.lower() in boilerplate


def test_heading_repetido_de_verdad_sigue_funcionando_sin_la_señal_confirmada() -> None:
    """No regresión: el mecanismo original (frecuencia) sigue andando para el
    caso de Rosario, donde nunca hubo comentario PageHeader de por medio."""
    membrete_rosario = "municipalidad de rosario"
    blocks = [
        {"page_number": p, "heading_level": 1, "content": "Municipalidad de Rosario"}
        for p in range(1, 11)
    ]

    boilerplate = _detect_repeated_heading_boilerplate(blocks)

    assert membrete_rosario in boilerplate


# ---------------------------------------------------------------------------
# Pipeline completo: el membrete no queda como heading_path de ningún chunk
# ---------------------------------------------------------------------------


def test_pipeline_completo_descarta_el_membrete_inconsistente() -> None:
    markdown = _markdown_con_membrete_inconsistente()
    blocks, heading_levels_by_order, _table_positions = _parse_markdown_blocks(markdown)
    for block in blocks:
        level = heading_levels_by_order.get(block["source_order"])
        if level is not None:
            block["heading_level"] = level

    intermediate = _to_intermediate_blocks(blocks)

    for chunk in intermediate:
        assert MEMBRETE not in (chunk.get("heading_path") or [])
        assert chunk["content"].strip() != MEMBRETE


# ---------------------------------------------------------------------------
# `_drop_page_counters`
# ---------------------------------------------------------------------------


def test_hoja_n_de_m_se_descarta_sin_importar_el_numero() -> None:
    bloques = [
        {"content": f"HOJA\n{n} de 22", "page_number": n, "source_order": 0}
        for n in range(1, 6)
    ]

    resultado = _drop_page_counters(bloques)

    assert resultado == []


def test_variantes_de_pagina_y_barra_tambien_se_descartan() -> None:
    bloques = [
        {"content": "Página 3/10", "page_number": 3, "source_order": 0},
        {"content": "Pag. 5 de 10", "page_number": 5, "source_order": 0},
        {"content": "PAGINA Nº 7 de 10", "page_number": 7, "source_order": 0},
    ]

    resultado = _drop_page_counters(bloques)

    assert resultado == []


def test_contenido_real_que_menciona_pagina_en_una_oracion_no_se_toca() -> None:
    """Guarda: el patrón exige que el bloque sea SOLO el contador, no que la
    palabra "página" aparezca en cualquier lado del texto."""
    bloques = [
        {
            "content": "El oferente debe numerar cada página de su oferta técnica de acuerdo al índice.",
            "page_number": 1,
            "source_order": 0,
        }
    ]

    assert _drop_page_counters(bloques) == bloques


def test_headings_no_se_tocan_aunque_matcheen_el_patron() -> None:
    """Mismo criterio que `_drop_repeated_page_furniture`: esta función es
    para párrafos de cuerpo, no para encabezados reales."""
    bloques = [{"content": "Hoja 1 de 22", "page_number": 1, "source_order": 0, "heading_level": 1}]

    assert _drop_page_counters(bloques) == bloques


def test_filas_de_tabla_no_se_tocan() -> None:
    bloques = [
        {
            "content": "Hoja 1 de 22",
            "page_number": 1,
            "source_order": 0,
            "row_order": 0,
            "block_type": "table",
            "table_ref": {"table_id": "T1"},
        }
    ]

    assert _drop_page_counters(bloques) == bloques
