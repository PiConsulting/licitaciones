from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Formularios y anexos que hay que completar y presentar sí o sí: planilla de "
    "cotización, declaración jurada, modelo de nota, formularios oficiales, "
    "documentación técnica obligatoria que integra la oferta."
)


def extractor_anexos_obligatorios(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="anexos_obligatorios",
        state_field="anexos",
        status_field="anexos_status",
        prompt_file_name="anexos_obligatorios.txt",
        query=_QUERY,
    )
