from __future__ import annotations

from analysis.extraction.highlight.ocr_regions import regiones_desde_renglones_ocr


def test_regiones_ocr_tolera_citation_con_gap_marker() -> None:
    renglones = [
        {
            "t": "La adjudicataria deberá ejecutar los trabajos necesarios para mitigar la causa del conflicto",
            "x": 50.0,
            "y": 100.0,
            "width": 500.0,
            "height": 12.0,
        },
        {
            "t": "dentro del plazo de siete (7) días hábiles desde la notificación.",
            "x": 50.0,
            "y": 116.0,
            "width": 500.0,
            "height": 12.0,
        },
    ]

    citation = "deberá ejecutar los trabajos necesarios [...] dentro del plazo de siete (7) días"
    regions = regiones_desde_renglones_ocr(renglones, citation)

    assert len(regions) > 0