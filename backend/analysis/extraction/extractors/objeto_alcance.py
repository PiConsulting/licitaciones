from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Objeto y alcance completos de la contratación: tipo de procedimiento, qué se compra/contrata, "
    "ítems y cantidades (renglones/lotes), organismo destinatario y modalidad de adjudicación "
    "(por ítem/global/lote), sin incluir plazos, garantías, causales, criterios ni requisitos formales."
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
