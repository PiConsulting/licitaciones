from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Cómo se evalúan las ofertas: método de adjudicación (menor precio, puntaje "
    "ponderado), ponderación precio vs. técnica, criterios con sus porcentajes, "
    "puntaje técnico mínimo, fórmula de evaluación."
)


def extractor_criterios_evaluacion(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="criterios_evaluacion",
        state_field="criterios",
        status_field="criterios_status",
        prompt_file_name="criterios_evaluacion.txt",
        query=_QUERY,
    )
