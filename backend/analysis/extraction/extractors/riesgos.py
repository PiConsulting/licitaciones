from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Riesgos de descalificación, penalizaciones, incumplimientos contractuales, "
    "consecuencias legales u operativas que puedan afectar la participación o "
    "ejecución del contrato, sin incluir plazos, garantías, causales o requisitos formales."
)


def extractor_riesgos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="riesgos",
        state_field="riesgos",
        status_field="riesgos_status",
        prompt_file_name="riesgos.txt",
        query=_QUERY,
    )
