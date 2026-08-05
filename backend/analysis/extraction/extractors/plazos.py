from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_plazos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="plazos",
        state_field="plazos",
        status_field="plazos_status",
        prompt_file_name="plazos_clave.txt",
        query="plazos fecha presentación ofertas apertura adjudicación vigencia",
        section_key="plazos",
        glossary_key="plazos_clave",
    )
