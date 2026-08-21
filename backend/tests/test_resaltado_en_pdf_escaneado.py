"""HL-09, paso 2: resaltar en PDF escaneados sin tocar los que ya andan.

Medido en el análisis de Santa Fe (`18a86363-…`):

    ANEXO V   (8bcb0e72)   6 / 6 fuentes con resaltado
    ANEXO III (e7a8d85d)   4 / 4
    ANEXO IV  (c7ebfe58)   3 / 3
    Pliego    (ebe9dca5)   0 / 2     <-- escaneado
    Anexo 2   (2af5720e)   0 / 3     <-- escaneado

`compute_highlight_regions` usa PyMuPDF `search_for`, que sólo encuentra texto
EMBEBIDO. Azure DI hace OCR, así que el análisis sale completo y el resaltado
sale vacío. Y el fallback del visor --decorar la capa de texto de react-pdf,
`PDFPage.tsx:83`-- también está vacío en un escaneo: no se ve nada.

La restricción de este cambio, y lo que más se prueba acá: **en un PDF con capa
de texto no puede cambiar nada**. Por eso la compuerta no es "la búsqueda viva
falló" sino "la búsqueda viva falló Y esta página no tiene texto embebido".
"""

from __future__ import annotations

import json
from typing import Any

from analysis.extraction.highlight import (
    _renglones_del_chunk,
    pagina_sin_capa_de_texto,
    regiones_desde_renglones_ocr,
)

# Un párrafo de tres renglones, con la geometría que deja `_build_line_index`.
# Anchos elegidos para que la aritmética proporcional dé números redondos.
RENGLONES: list[dict[str, Any]] = [
    {"x": 100.0, "y": 200.0, "width": 100.0, "height": 10.0, "t": "AAAAAAAAAA"},
    {"x": 100.0, "y": 212.0, "width": 100.0, "height": 10.0, "t": "BBBBBBBBBB"},
    {"x": 100.0, "y": 224.0, "width": 100.0, "height": 10.0, "t": "CCCCCCCCCC"},
]


# ---------------------------------------------------------------------------
# El matcher por renglones
# ---------------------------------------------------------------------------


def test_una_cita_de_un_solo_renglon_da_un_rectangulo_de_ese_renglon() -> None:
    regiones = regiones_desde_renglones_ocr(RENGLONES, "BBBBBBBBBB")

    assert regiones == [{"x": 100.0, "y": 212.0, "width": 100.0, "height": 10.0}]


def test_no_devuelve_el_parrafo_entero() -> None:
    """Es la diferencia con el camino que HL-08 sacó: un rectángulo por renglón
    tocado, no uno que cubre los tres."""
    regiones = regiones_desde_renglones_ocr(RENGLONES, "BBBBBBBBBB")

    assert len(regiones) == 1
    assert regiones[0]["height"] == 10.0  # no 34, que es el alto del párrafo


def test_una_cita_que_cruza_renglones_da_un_rectangulo_por_renglon() -> None:
    """Igual que PyMuPDF, que emite un rect por renglón tocado."""
    regiones = regiones_desde_renglones_ocr(RENGLONES, "AAAAAAAAAABBBBBBBBBB")

    assert [r["y"] for r in regiones] == [200.0, 212.0]


def test_el_primer_renglon_se_recorta_por_la_izquierda() -> None:
    """La cita arranca en la mitad del renglón: el rectángulo también."""
    renglones = [{"x": 100.0, "y": 200.0, "width": 100.0, "height": 10.0, "t": "ABCDEFGHIJ"}]

    regiones = regiones_desde_renglones_ocr(renglones, "FGHIJ")

    assert regiones == [{"x": 150.0, "y": 200.0, "width": 50.0, "height": 10.0}]


def test_el_ultimo_renglon_se_recorta_por_la_derecha() -> None:
    renglones = [{"x": 100.0, "y": 200.0, "width": 100.0, "height": 10.0, "t": "ABCDEFGHIJ"}]

    regiones = regiones_desde_renglones_ocr(renglones, "ABCDE")

    assert regiones == [{"x": 100.0, "y": 200.0, "width": 50.0, "height": 10.0}]


def test_los_renglones_del_medio_van_enteros() -> None:
    """Ahí el recorte proporcional no aplica y sería una aproximación gratis."""
    regiones = regiones_desde_renglones_ocr(RENGLONES, "AAAAABBBBBBBBBBCCCCC")

    del_medio = [r for r in regiones if r["y"] == 212.0][0]
    assert del_medio["x"] == 100.0
    assert del_medio["width"] == 100.0


def test_ignora_acentos_mayusculas_y_los_escapes_de_markdown() -> None:
    """La cita viene del markdown de DI, que escapa la puntuación (`3\\.`), y el
    renglón viene del OCR crudo. Sin plegar, nunca matchearían (ING-11/ING-12)."""
    renglones = [
        {"x": 0.0, "y": 0.0, "width": 100.0, "height": 10.0,
         "t": "3. Que se acepta la competencia y jurisdicción"}
    ]

    regiones = regiones_desde_renglones_ocr(renglones, "3\\. Que se acepta la COMPETENCIA y jurisdiccion")

    assert len(regiones) == 1


def test_una_cita_que_no_esta_no_devuelve_nada() -> None:
    """Antes que un rectángulo en el lugar equivocado, ninguno."""
    assert regiones_desde_renglones_ocr(RENGLONES, "esto no está en ningún renglón") == []


def test_sin_renglones_o_sin_cita_no_devuelve_nada() -> None:
    assert regiones_desde_renglones_ocr([], "BBBBBBBBBB") == []
    assert regiones_desde_renglones_ocr(RENGLONES, "") == []
    assert regiones_desde_renglones_ocr(RENGLONES, "   ") == []


def test_un_renglon_con_geometria_corrupta_se_saltea() -> None:
    renglones = [{"t": "BBBBBBBBBB"}, *RENGLONES]

    assert regiones_desde_renglones_ocr(renglones, "CCCCCCCCCC")


# ---------------------------------------------------------------------------
# De dónde salen los renglones
# ---------------------------------------------------------------------------


def _chunk_con_renglones(page: int = 1) -> dict[str, Any]:
    return {
        "source": json.dumps(
            {
                "page": page,
                "blocks": [
                    {
                        "para_id": [page, 4],
                        "bbox": [{"page": page, "x": 100.0, "y": 200.0, "width": 100.0, "height": 34.0}],
                        "content": "…",
                        "lines": RENGLONES,
                    }
                ],
            }
        )
    }


def test_los_renglones_se_leen_del_source_del_chunk() -> None:
    assert _renglones_del_chunk(_chunk_con_renglones(), 1) == RENGLONES


def test_un_bloque_de_otra_pagina_no_aporta_renglones() -> None:
    """Un chunk puede cruzar el corte de página; sus renglones no son
    intercambiables."""
    assert _renglones_del_chunk(_chunk_con_renglones(2), 1) == []


def test_un_chunk_sin_geometria_devuelve_vacio() -> None:
    """Todo lo indexado antes de este cambio."""
    viejo = {"source": json.dumps({"page": 1, "blocks": [{"bbox": [], "content": "…"}]})}

    assert _renglones_del_chunk(viejo, 1) == []
    assert _renglones_del_chunk(None, 1) == []
    assert _renglones_del_chunk({"source": "esto no es json"}, 1) == []
    assert _renglones_del_chunk({}, 1) == []


# ---------------------------------------------------------------------------
# La compuerta: si el PDF tiene texto, este camino no existe
# ---------------------------------------------------------------------------


def _pdf(tmp_path: Any, con_texto: bool) -> str:
    import fitz

    documento = fitz.open()
    pagina = documento.new_page()
    if con_texto:
        pagina.insert_text((72, 100), "CONTRATACION DIRECTA EE-2026-00055381")
    ruta = str(tmp_path / ("con_texto.pdf" if con_texto else "escaneado.pdf"))
    documento.save(ruta)
    documento.close()
    return ruta


def test_una_pagina_sin_texto_se_detecta(tmp_path: Any) -> None:
    assert pagina_sin_capa_de_texto(_pdf(tmp_path, con_texto=False), 1) is True


def test_una_pagina_con_texto_no_se_detecta_como_escaneada(tmp_path: Any) -> None:
    """Si esto diera True, el camino OCR se activaría en documentos que hoy
    andan bien. Es la garantía de "no romper lo que funciona"."""
    assert pagina_sin_capa_de_texto(_pdf(tmp_path, con_texto=True), 1) is False


def test_ante_la_duda_dice_que_tiene_texto(tmp_path: Any) -> None:
    """Conservador a propósito: cualquier error se resuelve por el camino de
    siempre, nunca activando el nuevo."""
    assert pagina_sin_capa_de_texto("", 1) is False
    assert pagina_sin_capa_de_texto("/no/existe.pdf", 1) is False
    # Página fuera de rango.
    assert pagina_sin_capa_de_texto(_pdf(tmp_path, con_texto=False), 99) is False
    assert pagina_sin_capa_de_texto(_pdf(tmp_path, con_texto=False), 0) is False


# ---------------------------------------------------------------------------
# Punta a punta, con el cableado real
# ---------------------------------------------------------------------------


def _fuente(page: int = 1) -> dict[str, Any]:
    return {
        "id": 0,
        "document_id": "doc-escaneado",
        "page_number": page,
        "citation": "BBBBBBBBBB",
        "chunk_id": "chunk-1",
    }


def test_en_un_escaneado_la_fuente_sale_con_regiones(tmp_path: Any) -> None:
    from analysis.extraction.highlight import compute_highlights_for_sources

    chunk = dict(_chunk_con_renglones(), id="chunk-1", document_id="doc-escaneado", page_number=1)
    enriquecidas = compute_highlights_for_sources(
        sources=[_fuente()],
        document_id_to_blob_path={"doc-escaneado": _pdf(tmp_path, con_texto=False)},
        correlation_id="test",
        chunks_by_doc_page={("doc-escaneado", 1): [chunk]},
    )

    assert enriquecidas[0]["highlight_regions"] == [
        {"x": 100.0, "y": 212.0, "width": 100.0, "height": 10.0}
    ]


def test_en_un_escaneado_sin_geometria_se_dice_por_que(tmp_path: Any) -> None:
    """El caso que antes era indistinguible de "no encontré la cita"."""
    from analysis.extraction.highlight import compute_highlights_for_sources

    chunk = {"id": "chunk-1", "document_id": "doc-escaneado", "page_number": 1,
             "source": json.dumps({"page": 1, "blocks": []})}
    enriquecidas = compute_highlights_for_sources(
        sources=[_fuente()],
        document_id_to_blob_path={"doc-escaneado": _pdf(tmp_path, con_texto=False)},
        correlation_id="test",
        chunks_by_doc_page={("doc-escaneado", 1): [chunk]},
    )

    assert enriquecidas[0]["highlight_regions"] == []
    assert enriquecidas[0]["highlight_unavailable_reason"] == "documento_escaneado"


def test_en_un_pdf_con_texto_una_cita_que_no_esta_sigue_saliendo_vacia(tmp_path: Any) -> None:
    """LA prueba de la restricción. El chunk TIENE geometría por renglón que
    haría match, y aun así no se usa: el PDF tiene capa de texto, así que el
    camino OCR no se toca y el visor sigue marcando sobre esa capa como hasta
    ahora. Sin la compuerta, este test devuelve regiones."""
    from analysis.extraction.highlight import compute_highlights_for_sources

    chunk = dict(_chunk_con_renglones(), id="chunk-1", document_id="doc-con-texto", page_number=1)
    enriquecidas = compute_highlights_for_sources(
        sources=[dict(_fuente(), document_id="doc-con-texto")],
        document_id_to_blob_path={"doc-con-texto": _pdf(tmp_path, con_texto=True)},
        correlation_id="test",
        chunks_by_doc_page={("doc-con-texto", 1): [chunk]},
    )

    assert enriquecidas[0]["highlight_regions"] == []
    assert "highlight_unavailable_reason" not in enriquecidas[0]


def test_el_motivo_sobrevive_a_la_revalidacion_de_la_narrativa() -> None:
    """`enrich_narrative_with_highlights` revalida con
    `CategoryNarrative.model_validate`, así que un campo no declarado se cae en
    silencio -- el mismo bug que ya costó `unverified` y `chunk_id` (ATR-05).
    Sin este test, el motivo se escribía y nunca llegaba al frontend."""
    from analysis.extraction.schemas import NarrativeSource

    fuente = NarrativeSource.model_validate(
        {
            "id": 0,
            "document_id": "doc-escaneado",
            "page_number": 1,
            "citation": "una cita cualquiera del pliego escaneado",
            "highlight_regions": [],
            "highlight_unavailable_reason": "documento_escaneado",
        }
    )

    assert fuente.highlight_unavailable_reason == "documento_escaneado"
    assert fuente.model_dump()["highlight_unavailable_reason"] == "documento_escaneado"


def test_una_fuente_normal_no_lleva_motivo() -> None:
    from analysis.extraction.schemas import NarrativeSource

    fuente = NarrativeSource.model_validate(
        {"id": 0, "document_id": "d", "page_number": 1, "citation": "una cita cualquiera del pliego"}
    )

    assert fuente.highlight_unavailable_reason is None
