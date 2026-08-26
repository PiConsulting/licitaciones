from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Todos los anexos numerados que integran el pliego y son obligatorios para "
    "el oferente (Anexo I, II, III, IV, V, VI...): tanto formularios para "
    "completar (planilla de cotización, declaración jurada, modelo de nota, "
    "formularios oficiales) como anexos instructivos o técnicos que no se "
    "completan pero igual son parte obligatoria de la oferta (requisitos a "
    "cumplimentar, antecedentes técnicos de los oferentes, presentación "
    "técnica de las ofertas, plan de trabajo). Cualquier sección titulada "
    "'Anexo [número/letra]' que el pliego declare parte integrante del "
    "procedimiento."
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
