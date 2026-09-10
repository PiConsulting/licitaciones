from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

# 2026-09-10: versión corta — la larga con la coletilla "típicamente en la
# carátula o los primeros artículos" medía 0.879 vs 0.907 de esta.
_QUERY = (
    "Organismo convocante, número de expediente, tipo de procedimiento, "
    "presupuesto oficial, jurisdicción"
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
