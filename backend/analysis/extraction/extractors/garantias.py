from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_garantias(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="garantias",
        state_field="garantias",
        status_field="garantias_status",
        prompt_file_name="garantias.txt",
        query="garantía oferta cumplimiento anticipo monto caución seguro",
        section_key="garantias",
        glossary_key="garantias",
    )
