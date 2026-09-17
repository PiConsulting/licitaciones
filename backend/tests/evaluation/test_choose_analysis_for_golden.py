# Regresión (2026-09-14, Fase 2 de la auditoría RAG): `_choose_analysis_for_golden`
# rechazaba un match solo si `quote_score == 0` -- una sola cita literal
# coincidente (por azar, con una frase corta y genérica) alcanzaba para
# aceptar un match falso. Medido con los 8 análisis golden reales: los
# matches genuinos tienen `quote_score` entre 23 y 54; un golden cuyo pliego
# real no está indexado (`corrientes_licencias.md`) matcheaba con
# `quote_score=1` contra un análisis sin ninguna relación real.
from __future__ import annotations

from scripts.evaluation.build_dataset_from_golden_md import (
    _MIN_QUOTE_SCORE_TO_TRUST,
    _choose_analysis_for_golden,
)


def _chunks_with_content(*texts: str) -> list[dict]:
    return [{"content": text} for text in texts]


def test_una_sola_cita_coincidente_no_alcanza_para_confiar() -> None:
    """Un golden cuyo pliego real no está indexado puede igual compartir UNA
    frase corta y genérica con un análisis sin relación -- no debe matchear."""
    md_text = '- "Presentación de ofertas en formato PDF sin enmiendas"'
    chunks_by_analysis = {
        "analysis-sin-relacion": _chunks_with_content(
            "Presentación de ofertas en formato PDF sin enmiendas",
            "contenido irrelevante que no aparece en el golden",
        ),
    }

    best_id, ranking = _choose_analysis_for_golden(md_text, chunks_by_analysis)

    assert best_id is None
    assert ranking["analysis-sin-relacion"]["quote_score"] == 1


def test_muchas_citas_coincidentes_si_matchea() -> None:
    """Un match genuino tiene MUCHAS citas literales confirmadas, no una."""
    quotes = [f"Cláusula número {i} del pliego particular de este expediente" for i in range(10)]
    md_text = "\n".join(f'- "{q}"' for q in quotes)
    chunks_by_analysis = {
        "analysis-real": _chunks_with_content(*quotes),
        "analysis-otro": _chunks_with_content("contenido sin relación"),
    }

    best_id, ranking = _choose_analysis_for_golden(md_text, chunks_by_analysis)

    assert best_id == "analysis-real"
    assert ranking["analysis-real"]["quote_score"] == 10
    assert ranking["analysis-real"]["quote_score"] >= _MIN_QUOTE_SCORE_TO_TRUST


def test_sin_ninguna_cita_no_matchea() -> None:
    md_text = "Texto sin ninguna cita entre comillas."
    chunks_by_analysis = {"analysis-1": _chunks_with_content("contenido cualquiera")}

    best_id, ranking = _choose_analysis_for_golden(md_text, chunks_by_analysis)

    assert best_id is None
