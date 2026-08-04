from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_cronograma_proceso(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="cronograma_proceso",
        state_field="cronograma",
        status_field="cronograma_status",
        prompt_file_name="cronograma_proceso.txt",
        query="cronograma etapas fechas timeline proceso licitatorio",
        section_key="cronograma_proceso",
    )
