"""CHK-15: el membrete de página se indexaba como contenido y como contexto de tabla.

`_detect_repeated_heading_boilerplate` ya filtra el membrete cuando Document
Intelligence lo marca como encabezado -- fue el caso del pliego de Rosario, donde
la razón social del organismo venía como título de nivel 1 en cada página. Su
propio docstring aclara que un párrafo de cuerpo repetido no entra en ese
chequeo.

En el PET de Bancor el membrete viene exactamente así: como párrafo. El
resultado, en el análisis `f33897ba`, fue un chunk entero de 40 caracteres que
dice `BANCO DE LA PROVINCIA DE CÓRDOBA / BANCOR`, y ese mismo texto encabezando
los chunks de tabla como si fuera la frase que las introduce.

El riesgo del fix es descartar una cláusula real del pliego, así que se exigen
dos condiciones juntas: que sea corto Y que se repita en la mayoría de las
páginas. Una cláusula con contenido no cumple las dos a la vez.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import _drop_repeated_page_furniture, create_chunks

MEMBRETE = "BANCO DE LA PROVINCIA DE CÓRDOBA"
LOGO = "BANCOR"


def _parrafo(contenido: str, page: int, source_order: int = 0) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


def _pliego_con_membrete(paginas: int = 10) -> list[dict[str, Any]]:
    bloques: list[dict[str, Any]] = []
    for pagina in range(1, paginas + 1):
        bloques.append(_parrafo(MEMBRETE, pagina, 0))
        bloques.append(_parrafo(LOGO, pagina, 1))
        bloques.append(
            _parrafo(
                f"Artículo {pagina}. Texto sustantivo y distinto en cada página del pliego, "
                "con la extensión suficiente para producir un chunk propio.",
                pagina,
                2,
            )
        )
    return bloques


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_el_membrete_repetido_se_descarta() -> None:
    resultado = _drop_repeated_page_furniture(_pliego_con_membrete())

    contenidos = [b["content"] for b in resultado]
    assert MEMBRETE not in contenidos
    assert LOGO not in contenidos


def test_el_texto_real_de_cada_pagina_sobrevive() -> None:
    resultado = _drop_repeated_page_furniture(_pliego_con_membrete())

    assert len([b for b in resultado if b["content"].startswith("Artículo")]) == 10


def _pliego_con_membrete_pegado_a_una_tabla() -> list[dict[str, Any]]:
    """La estructura real de Bancor: en la página de la tabla, el membrete es lo
    único que la precede.

    Importa reproducirla. Si entre el membrete y la tabla hay un párrafo de
    cuerpo, `_merge_intermediate_blocks` los fusiona y el membrete deja de
    quedar solo -- con esa forma el test pasa aunque el filtro no exista.
    """
    bloques = _pliego_con_membrete()
    bloques = [b for b in bloques if not (b["page_number"] == 4 and b["source_order"] == 2)]
    for orden in range(3):
        bloques.append(
            {
                "content": f"col_1: Concepto {orden}\ncol_2: Valor {orden}",
                "page_number": 4,
                "source_order": 3,
                "row_order": orden,
                "block_type": "table",
                "table_ref": {"table_id": "T1"},
            }
        )
    return bloques


def test_el_pipeline_no_produce_un_chunk_que_es_solo_membrete() -> None:
    chunks = create_chunks(_pliego_con_membrete_pegado_a_una_tabla(), document_id="doc", correlation_id="corr")

    assert chunks
    for chunk in chunks:
        contenido = chunk["content"].strip()
        assert contenido not in {MEMBRETE, LOGO, f"{MEMBRETE}\n\n{LOGO}"}, (
            f"quedó un chunk que es sólo membrete: {contenido!r}"
        )


def test_el_membrete_no_termina_como_contexto_de_una_tabla() -> None:
    """El síntoma concreto: los chunks de tabla de Bancor arrancaban con
    `BANCO DE LA PROVINCIA DE CÓRDOBA / BANCOR`."""
    chunks = create_chunks(_pliego_con_membrete_pegado_a_una_tabla(), document_id="doc", correlation_id="corr")
    tablas = [c for c in chunks if c["block_type"] == "table"]

    assert tablas
    for tabla in tablas:
        assert MEMBRETE not in tabla["content"]
        assert LOGO not in tabla["content"], "la tabla se llevó el logo del membrete como contexto"


# ---------------------------------------------------------------------------
# Guardas: lo que NO se puede descartar
# ---------------------------------------------------------------------------


def test_una_clausula_larga_repetida_no_se_descarta() -> None:
    """Un pliego puede repetir una cláusula en varias páginas. Si es larga,
    tiene contenido y hay que conservarla."""
    clausula = (
        "Posteriormente a la adjudicación no se aceptarán cargos adicionales, demoras, "
        "modificaciones de precio ni ningún otro concepto no previsto en la oferta original."
    )
    bloques = [_parrafo(clausula, pagina, 0) for pagina in range(1, 11)]
    bloques += [_parrafo(f"Texto propio de la página {p}.", p, 1) for p in range(1, 11)]

    assert len(_drop_repeated_page_furniture(bloques)) == len(bloques)


def test_un_texto_corto_que_aparece_en_pocas_paginas_no_es_membrete() -> None:
    """Dos apariciones no son un membrete: puede ser un dato repetido a
    propósito."""
    bloques = [_parrafo("Plazo: 45 días corridos.", pagina, 0) for pagina in (2, 5)]
    bloques += [_parrafo(f"Texto propio de la página {p}.", p, 1) for p in range(1, 11)]

    assert len(_drop_repeated_page_furniture(bloques)) == len(bloques)


def test_un_documento_de_pocas_paginas_no_se_toca() -> None:
    """Con dos páginas, "se repite en la mayoría" no significa nada."""
    bloques = [_parrafo("Texto corto", 1, 0), _parrafo("Texto corto", 2, 0)]

    assert len(_drop_repeated_page_furniture(bloques)) == 2


def test_los_encabezados_los_sigue_manejando_el_detector_de_siempre() -> None:
    """Esta función es para párrafos: no puede pisarse con
    `_detect_repeated_heading_boilerplate`, que tiene su propia lógica de
    recorte parcial del membrete dentro de un título."""
    bloques = [
        {"heading_level": 1, "content": MEMBRETE, "page_number": pagina, "source_order": 0}
        for pagina in range(1, 11)
    ]

    assert len(_drop_repeated_page_furniture(bloques)) == len(bloques)


def test_las_filas_de_tabla_no_se_evaluan_como_membrete() -> None:
    """Una columna con el mismo valor en muchas páginas es un dato, no un
    membrete."""
    bloques = [
        {
            "content": "col_1: Cumple",
            "page_number": pagina,
            "source_order": 0,
            "row_order": 0,
            "block_type": "table",
            "table_ref": {"table_id": f"T{pagina}"},
        }
        for pagina in range(1, 11)
    ]

    assert len(_drop_repeated_page_furniture(bloques)) == len(bloques)
