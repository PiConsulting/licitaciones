from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Garantías exigidas: mantenimiento de oferta, cumplimiento de contrato, anticipo, "
    "impugnación — montos o porcentajes, forma de constitución (póliza, cau ción, "
    "aval bancario, depósito), plazos de vigencia."
)


def extractor_garantias(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="garantias",
        state_field="garantias",
        status_field="garantias_status",
        prompt_file_name="garantias.txt",
        query=_QUERY,
    )
