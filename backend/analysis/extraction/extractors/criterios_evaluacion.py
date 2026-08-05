from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_criterios_evaluacion(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="criterios_evaluacion",
        state_field="criterios",
        status_field="criterios_status",
        prompt_file_name="criterios_evaluacion.txt",
        query="criterios evaluación ponderación puntaje oferta económica técnica",
        section_key="criterios_evaluacion",
        glossary_key="criterios_evaluacion",
    )
