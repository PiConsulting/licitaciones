from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_anexos_obligatorios(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="anexos_obligatorios",
        state_field="anexos",
        status_field="anexos_status",
        prompt_file_name="anexos_obligatorios.txt",
        query="anexo formulario apendice obligatorio firma completarse",
        section_key="anexos_obligatorios",
        glossary_key="anexos_obligatorios",
    )
