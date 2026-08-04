from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_causales(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="causales",
        state_field="causales",
        status_field="causales_status",
        prompt_file_name="causales.txt",
        query="causales rechazo inhabilita descalifica sanciones",
        section_key="causales_rechazo",
    )
