from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Documentación obligatoria para que la oferta no sea rechazada de entrada: "
    "inscripción en registros, certificados fiscales, habilitaciones, antecedentes, "
    "capacidad técnica y financiera, certificaciones del fabricante, experiencia "
    "comprobable, requisitos técnicos mínimos del oferente."
)


def extractor_requisitos_admisibilidad(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="requisitos_admisibilidad",
        state_field="requisitos_admisibilidad",
        status_field="requisitos_admisibilidad_status",
        prompt_file_name="requisitos_admisibilidad.txt",
        query=_QUERY,
    )
