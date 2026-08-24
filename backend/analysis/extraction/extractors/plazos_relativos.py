from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Plazos relativos expresados en función de eventos: "
    "días corridos o hábiles desde la apertura, después de la adjudicación, "
    "antes de la presentación. Duraciones y límites de tiempo contados desde "
    "eventos específicos del procedimiento o ejecución del contrato."
)


def extractor_plazos_relativos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="plazos_relativos",
        state_field="plazos_relativos",
        status_field="plazos_relativos_status",
        prompt_file_name="plazos_relativos.txt",
        query=_QUERY,
    )
