from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_objeto_alcance(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="objeto_alcance",
        state_field="objeto_alcance",
        status_field="objeto_alcance_status",
        prompt_file_name="objeto_alcance.txt",
        query="objeto alcance modalidad oferta parcial alternativas lugar de entrega plazo de ejecucion",
        section_key="objeto_alcance",
        glossary_key="objeto_alcance",
    )
