from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

# Query corta a propósito: una versión larga (~60 palabras) medía menos recall (0.917 vs 0.979) porque el embedding difumina el núcleo "anexo/formulario/planilla".
_QUERY = "Formularios y anexos que deben completarse y presentarse con la oferta"


def extractor_anexos_obligatorios(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="anexos_obligatorios",
        state_field="anexos",
        status_field="anexos_status",
        prompt_file_name="anexos_obligatorios.txt",
        query=_QUERY,
    )
