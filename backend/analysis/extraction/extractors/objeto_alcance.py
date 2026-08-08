from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Qué se licita: objeto de la contratación, modalidad (bienes, servicios, obra), "
    "lugar de entrega o prestación, plazo de ejecución, si se admiten ofertas parciales "
    "o alternativas."
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
