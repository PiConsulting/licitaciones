from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_identificacion_procedimiento(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="identificacion_procedimiento",
        state_field="identificacion",
        status_field="identificacion_status",
        prompt_file_name="identificacion_procedimiento.txt",
        query="organismo convocante expediente numero de procedimiento tipo de procedimiento jurisdiccion",
        section_key="identificacion_procedimiento",
        glossary_key="datos_procedimiento",
    )
