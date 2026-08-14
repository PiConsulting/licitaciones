"""Citas que ocupan varios renglones.

REGRESIÓN (auditoría 2026-08-13, detectada sobre un análisis real).

`page.search_for()` devuelve UN RECTÁNGULO POR RENGLÓN cuando el texto buscado
ocupa varias líneas. `compute_highlight_regions` interpretaba `len(instances) > 1`
como "el texto aparece en varios lugares" y llamaba a `_select_best_instance`,
que se queda con uno solo. Para una cita multilínea -- casi todas las de un
pliego -- se tiraban los demás renglones y a veces quedaba el fragmento más
chico.

Observado en producción: una cita de 154 caracteres resaltada con un recuadro
de `width: 8.93` px.
"""
from __future__ import annotations

import pytest

from analysis.extraction.highlight import _group_rects_by_occurrence, compute_highlight_regions


class _Rect:
    """Sustituto de fitz.Rect para probar la agrupación sin abrir un PDF."""

    def __init__(self, x0: float, y0: float, width: float, height: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.width = width
        self.height = height
        self.x1 = x0 + width


def test_renglones_consecutivos_son_una_sola_aparicion() -> None:
    # Medidas reales de una cita de 3 renglones (interlineado 12pt, alto 15.1pt).
    rects = [_Rect(60.0, 88.2, 318.5, 15.1), _Rect(60.0, 100.2, 314.2, 15.1), _Rect(60.0, 112.2, 120.5, 15.1)]

    groups = _group_rects_by_occurrence(rects)

    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_dos_rects_lejos_en_la_misma_altura_son_apariciones_distintas() -> None:
    """Caso real del pliego auditado: "GARANT" aparece dos veces en y=548.7,
    separadas por media página."""
    rects = [_Rect(129.5, 548.7, 40.0, 15.1), _Rect(482.3, 548.7, 40.0, 15.1)]

    groups = _group_rects_by_occurrence(rects)

    assert len(groups) == 2


def test_fragmentos_contiguos_del_mismo_renglon_son_una_sola_aparicion() -> None:
    """Medidas exactas del pliego auditado: la cita "c) Propuesta Técnica..."
    se parte en "c)" (ancho 8.9) + el resto del renglón, separados por 3.1 px.
    Ese primer fragmento de 8.9 px era el que llegaba a producción."""
    rects = [
        _Rect(56.8, 448.5, 8.9, 11.5),    # "c)"
        _Rect(68.8, 448.5, 469.4, 11.5),  # resto del renglón 1
        _Rect(56.8, 460.0, 242.3, 11.5),  # renglón 2
    ]

    groups = _group_rects_by_occurrence(rects)

    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_rects_lejanos_verticalmente_son_apariciones_distintas() -> None:
    rects = [_Rect(60.0, 100.0, 300.0, 15.1), _Rect(60.0, 500.0, 300.0, 15.1)]

    groups = _group_rects_by_occurrence(rects)

    assert len(groups) == 2


def test_grupo_vacio_no_rompe() -> None:
    assert _group_rects_by_occurrence([]) == []


# ---------------------------------------------------------------------------
# End to end sobre un PDF generado con la misma forma que el pliego real
# ---------------------------------------------------------------------------

_CITA_LARGA = (
    "c) Propuesta Tecnica debidamente firmada: La propuesta tecnica debera contener "
    "las caracteristicas tecnicas segun los requisitos detallados en el Anexo I."
)


@pytest.fixture
def pdf_con_cita_multilinea(tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "c) Propuesta Tecnica debidamente firmada: La propuesta tecnica")
    page.insert_text((60, 112), "debera contener las caracteristicas tecnicas segun los requisitos")
    page.insert_text((60, 124), "detallados en el Anexo I.")
    path = tmp_path / "multilinea.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def test_una_cita_de_tres_renglones_devuelve_tres_regiones(pdf_con_cita_multilinea) -> None:
    regions = compute_highlight_regions(
        pdf_con_cita_multilinea, page_number=1, citation=_CITA_LARGA, correlation_id="ml"
    )

    assert len(regions) == 3, f"se perdieron renglones: {regions}"


def test_el_resaltado_cubre_el_ancho_real_de_la_cita(pdf_con_cita_multilinea) -> None:
    """El síntoma reportado: un recuadro de 8.93 px para una cita de 154 chars."""
    regions = compute_highlight_regions(
        pdf_con_cita_multilinea, page_number=1, citation=_CITA_LARGA, correlation_id="ml"
    )

    assert max(region["width"] for region in regions) > 200, (
        f"el resaltado más ancho mide {max(r['width'] for r in regions):.1f} px "
        "para una cita de 154 caracteres"
    )


def test_con_section_hint_no_se_pierden_los_renglones(pdf_con_cita_multilinea) -> None:
    """El section_hint debe desambiguar ENTRE apariciones, no entre renglones."""
    regions = compute_highlight_regions(
        pdf_con_cita_multilinea,
        page_number=1,
        citation=_CITA_LARGA,
        correlation_id="ml",
        section_hint="requisitos admisibilidad",
    )

    assert len(regions) == 3


def test_con_dos_apariciones_se_resalta_una_sola(tmp_path) -> None:
    """Pintar varias apariciones a la vez es peor que pintar una: parece que el
    sistema está seguro (hallazgo HL-04)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "conforme lo establecido en el presente pliego")
    page.insert_text((60, 500), "conforme lo establecido en el presente pliego")
    path = tmp_path / "dos.pdf"
    doc.save(str(path))
    doc.close()

    regions = compute_highlight_regions(
        str(path),
        page_number=1,
        citation="conforme lo establecido en el presente pliego",
        correlation_id="ml",
    )

    assert len(regions) == 1
    # La primera en orden de lectura.
    assert regions[0]["y"] < 200


def test_los_fragmentos_por_span_se_unen_por_renglon(pdf_con_cita_multilinea) -> None:
    """PyMuPDF parte el match por span: una cita de 198 caracteres puede volver
    en 24 rectangulitos contiguos. Son correctos, pero el visor tendría que
    dibujar 24 recuadros pegados para representar 3 renglones."""
    regions = compute_highlight_regions(
        pdf_con_cita_multilinea, page_number=1, citation=_CITA_LARGA, correlation_id="ml"
    )

    # Un recuadro por renglón, no uno por fragmento.
    assert len(regions) == 3
    ys = [region["y"] for region in regions]
    assert ys == sorted(ys), "los renglones deben venir en orden de lectura"
    assert len(set(round(y) for y in ys)) == 3, "no puede haber dos recuadros en el mismo renglón"


def test_unir_por_renglon_no_pierde_superficie(pdf_con_cita_multilinea) -> None:
    """La unión es de presentación: tiene que cubrir al menos lo mismo."""
    import fitz

    doc = fitz.open(pdf_con_cita_multilinea)
    raw_rects = doc[0].search_for(_CITA_LARGA)
    doc.close()

    regions = compute_highlight_regions(
        pdf_con_cita_multilinea, page_number=1, citation=_CITA_LARGA, correlation_id="ml"
    )

    for rect in raw_rects:
        cubierto = any(
            region["x"] - 0.5 <= rect.x0
            and region["x"] + region["width"] + 0.5 >= rect.x1
            and region["y"] - 0.5 <= rect.y0
            for region in regions
        )
        assert cubierto, f"el fragmento {rect} quedó fuera de los recuadros unidos"
