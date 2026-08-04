from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_documentos_requeridos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="documentos_requeridos",
        state_field="documentos",
        status_field="documentos_status",
        prompt_file_name="documentos_requeridos.txt",
        query="documentos documentación requisitos formularios certificados",
        section_key="documentos_requeridos",
    )
