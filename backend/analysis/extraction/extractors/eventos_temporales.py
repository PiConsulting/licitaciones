from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Eventos, hitos y plazos temporales del proceso de licitación: fechas "
    "explícitas (recepción del pliego, apertura, adjudicación, firma de "
    "contrato, entregas) y plazos contados desde esos eventos ('X días "
    "corridos/hábiles desde...', 'dentro de los X días de...'). Tanto "
    "hitos con fecha propia como plazos que dependen de otro evento."
)


def extractor_eventos_temporales(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="eventos_temporales",
        state_field="eventos_temporales",
        status_field="eventos_temporales_status",
        prompt_file_name="eventos_temporales.txt",
        query=_QUERY,
    )
