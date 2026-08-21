from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Datos de identificación del procedimiento: organismo o jurisdicción convocante, número "
    "de expediente, número y tipo de procedimiento (licitación pública, privada, concurso, "
    "contratación directa), presupuesto oficial y jurisdicción — típicamente en la carátula o los primeros "
    "artículos del pliego."
)


def extractor_identificacion_procedimiento(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="identificacion_procedimiento",
        state_field="identificacion",
        status_field="identificacion_status",
        prompt_file_name="identificacion_procedimiento.txt",
        query=_QUERY,
    )
