from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_requisitos_admisibilidad(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="requisitos_admisibilidad",
        state_field="requisitos_admisibilidad",
        status_field="requisitos_admisibilidad_status",
        prompt_file_name="requisitos_admisibilidad.txt",
        query=(
            "requisitos de admisibilidad documentos obligatorios "
            "restricciones de participación inhabilitaciones experiencia mínima"
        ),
        section_key="requisitos_admisibilidad",
        glossary_key="requisitos_admisibilidad",
    )
