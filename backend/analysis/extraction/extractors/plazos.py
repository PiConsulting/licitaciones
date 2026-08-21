from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Fechas y plazos clave: apertura de ofertas, presentación de ofertas, "
    "mantenimiento de oferta, plazo de entrega o ejecución, consultas, "
    "impugnaciones, adjudicación, firma de contrato."
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
