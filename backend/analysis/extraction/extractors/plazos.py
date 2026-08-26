from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Plazos y vencimientos que el oferente o adjudicatario debe cumplir: "
    "cuando presentar ofertas, cuando se abre, cuanto dura la oferta, "
    "cuando entregar, cuando firmar contrato. Fechas limites y duraciones "
    "de actos del procedimiento y la ejecucion del contrato."
)


def extractor_plazos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="plazos_clave",
        state_field="plazos",
        status_field="plazos_status",
        prompt_file_name="plazos_clave.txt",
        query=_QUERY,
    )
