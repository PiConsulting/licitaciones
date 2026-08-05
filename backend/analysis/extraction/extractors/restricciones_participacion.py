from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_restricciones_participacion(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="restricciones_participacion",
        state_field="restricciones",
        status_field="restricciones_status",
        prompt_file_name="requisitos_admisibilidad_restricciones.txt",
        query="restricciones requisitos capacidad experiencia habilitación certificación",
        section_key="restricciones_participacion",
        glossary_key="requisitos_admisibilidad",
    )
