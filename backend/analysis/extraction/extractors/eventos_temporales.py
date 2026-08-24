from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Eventos temporales y hitos del proceso de licitación: "
    "fechas de recepción del pliego, apertura de ofertas, adjudicación, "
    "firma de contrato, inicio de obra, entregas. Cualquier evento o momento "
    "clave mencionado en el documento, con o sin fecha específica."
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
