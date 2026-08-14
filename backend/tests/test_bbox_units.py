"""Unidad de las coordenadas de bounding box.

REGRESIÓN ING-03 (auditoría 2026-08-13, confirmada sobre un análisis real).

Azure Document Intelligence expresa las coordenadas en la unidad de
`result.pages[i].unit`: PULGADAS para PDF. El pipeline las guardaba crudas,
mientras que el camino de highlighting con PyMuPDF emite PUNTOS. Los dos
alimentan el mismo campo `highlight_regions` y el visor multiplica por la
escala de zoom, así que las regiones en pulgadas se dibujaban como un recuadro
de ~7 px en el ángulo superior izquierdo.

Observado en producción, mezclado en la MISMA respuesta:
    {"x": 0.7731, "y": 2.1239, "width": 6.7108}   <- pulgadas (Azure DI)
    {"x": 56.79,  "y": 465.20, "width": 240.33}   <- puntos (PyMuPDF)
"""
from __future__ import annotations

import pytest

from extraction.document_intelligence import (
    _extract_bounding_boxes,
    _page_sizes_in_points,
    _page_unit_scales,
)


class _Region:
    def __init__(self, page_number: int, polygon: list[float]) -> None:
        self.page_number = page_number
        self.polygon = polygon


class _Item:
    def __init__(self, regions: list[_Region]) -> None:
        self.bounding_regions = regions


class _Page:
    def __init__(self, page_number: int, unit: str, width: float, height: float) -> None:
        self.page_number = page_number
        self.unit = unit
        self.width = width
        self.height = height


class _Result:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages


# A4 real del pliego auditado: 595.3 x 841.9 pt = 8.27 x 11.69 in
_A4_INCHES = _Result([_Page(1, "inch", 8.27, 11.69)])

# Bloque real del pliego (página 2, "Artículo 1: OBJETO"), en pulgadas.
_POLYGON_INCHES = [0.7731, 2.1239, 7.4839, 2.1239, 7.4839, 2.4621, 0.7731, 2.4621]


def test_las_pulgadas_de_azure_di_se_convierten_a_puntos() -> None:
    scales = _page_unit_scales(_A4_INCHES)
    bboxes = _extract_bounding_boxes(_Item([_Region(1, _POLYGON_INCHES)]), scales)

    assert len(bboxes) == 1
    bbox = bboxes[0]
    # 0.7731 in * 72 = 55.66 pt -- la misma escala que devuelve PyMuPDF.
    assert bbox["x"] == pytest.approx(55.66, abs=0.1)
    assert bbox["y"] == pytest.approx(152.92, abs=0.1)
    assert bbox["width"] == pytest.approx(483.18, abs=0.1)


def test_el_bbox_convertido_queda_en_la_misma_escala_que_pymupdf() -> None:
    """La prueba que importa: los dos caminos tienen que ser comparables."""
    scales = _page_unit_scales(_A4_INCHES)
    bbox = _extract_bounding_boxes(_Item([_Region(1, _POLYGON_INCHES)]), scales)[0]

    # Una página A4 mide 841.9 pt de alto. Un bloque que en pulgadas estaba a
    # 2.12 (de 11.69) tiene que caer alrededor del 18% de la altura.
    assert 0.15 < bbox["y"] / 841.9 < 0.22
    # Y en la escala vieja daba 2.12, que sobre 841.9 es el 0.25%: invisible.
    assert bbox["y"] > 100


def test_unidad_en_puntos_no_se_reescala() -> None:
    scales = _page_unit_scales(_Result([_Page(1, "point", 595.3, 841.9)]))
    bbox = _extract_bounding_boxes(_Item([_Region(1, [10.0, 20.0, 110.0, 20.0, 110.0, 40.0, 10.0, 40.0])]), scales)[0]

    assert bbox["x"] == pytest.approx(10.0)
    assert bbox["y"] == pytest.approx(20.0)


def test_unidad_desconocida_descarta_el_bbox_en_vez_de_emitirlo_mal() -> None:
    """Píxeles: no se puede convertir sin el DPI. Mejor sin resaltado que con
    uno en una escala que el consumidor no puede interpretar."""
    scales = _page_unit_scales(_Result([_Page(1, "pixel", 2480, 3508)]))

    assert scales == {}
    assert _extract_bounding_boxes(_Item([_Region(1, _POLYGON_INCHES)]), scales) == []


def test_paginas_con_unidades_distintas_se_convierten_por_separado() -> None:
    result = _Result([_Page(1, "inch", 8.27, 11.69), _Page(2, "point", 595.3, 841.9)])
    scales = _page_unit_scales(result)

    polygon = [1.0, 1.0, 2.0, 1.0, 2.0, 2.0, 1.0, 2.0]
    page1 = _extract_bounding_boxes(_Item([_Region(1, polygon)]), scales)[0]
    page2 = _extract_bounding_boxes(_Item([_Region(2, polygon)]), scales)[0]

    assert page1["x"] == pytest.approx(72.0)
    assert page2["x"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Validación de límites contra el tamaño real de la página
# ---------------------------------------------------------------------------


def test_page_sizes_se_calculan_en_puntos() -> None:
    scales = _page_unit_scales(_A4_INCHES)
    sizes = _page_sizes_in_points(_A4_INCHES, scales)

    width, height = sizes[1]
    assert width == pytest.approx(595.4, abs=1.0)
    assert height == pytest.approx(841.7, abs=1.0)


def test_un_bbox_fuera_de_la_hoja_se_descarta() -> None:
    from extraction.document_intelligence import _enrich_blocks_with_para_id

    blocks = [{"page_number": 1, "content": "texto", "source_order": 0}]
    fuera = [{"page": 1, "x": 50.0, "y": 5000.0, "width": 100.0, "height": 20.0}]

    _enrich_blocks_with_para_id(blocks, {(1, 0): fuera}, {1: (595.3, 841.9)})

    assert blocks[0]["bbox"] == []


def test_un_bbox_dentro_de_la_hoja_se_conserva() -> None:
    from extraction.document_intelligence import _enrich_blocks_with_para_id

    blocks = [{"page_number": 1, "content": "texto", "source_order": 0}]
    dentro = [{"page": 1, "x": 55.7, "y": 152.9, "width": 483.2, "height": 24.3}]

    _enrich_blocks_with_para_id(blocks, {(1, 0): dentro}, {1: (595.3, 841.9)})

    assert blocks[0]["bbox"] == dentro


def test_el_limite_viejo_hardcodeado_ya_no_decide() -> None:
    """Con los límites `x<=1200 / y<=1600`, un escaneo en píxeles (A4 a 300 DPI
    = 2480x3508) perdía el 100% de sus bbox. Ahora se valida contra la página."""
    from extraction.document_intelligence import _enrich_blocks_with_para_id

    blocks = [{"page_number": 1, "content": "texto", "source_order": 0}]
    grande = [{"page": 1, "x": 200.0, "y": 2000.0, "width": 1800.0, "height": 40.0}]

    _enrich_blocks_with_para_id(blocks, {(1, 0): grande}, {1: (2480.0, 3508.0)})

    assert blocks[0]["bbox"] == grande
