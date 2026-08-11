from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Qué se licita exactamente: objeto principal de la contratación y alcance general "
    "en síntesis breve (2-3 líneas), sin incluir plazos, garantías, causales de rechazo, "
    "criterios de evaluación ni requisitos formales."
)


def extractor_objeto_alcance(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="objeto_alcance",
        state_field="objeto_alcance",
        status_field="objeto_alcance_status",
        prompt_file_name="objeto_alcance.txt",
        query=_QUERY,
    )
