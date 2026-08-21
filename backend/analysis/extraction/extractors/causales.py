from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Motivos por los cuales una oferta se descalifica sin evaluarla: causales de "
    "rechazo formal, desestimación, exclusión, falta de documentación, garantía "
    "insuficiente, inhabilitación, presentación fuera de término, falsedad de datos."
)


def extractor_causales(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="causales_rechazo",
        state_field="causales",
        status_field="causales_status",
        prompt_file_name="causales_rechazo.txt",
        query=_QUERY,
    )
