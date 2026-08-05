from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState


def extractor_estimacion_presupuesto(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="estimacion_presupuesto",
        state_field="presupuesto",
        status_field="presupuesto_status",
        prompt_file_name="estimacion_presupuesto.txt",
        query="presupuesto oficial monto estimado valor referencia forma de pago",
        section_key="estimacion_presupuesto",
        is_object_result=True,
    )
