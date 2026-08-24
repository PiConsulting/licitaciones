from __future__ import annotations

from analysis.extraction.extractors.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Riesgos comerciales y de participación para el oferente: mantenimiento de "
    "oferta, moneda y tipo de cambio, forma de pago, alta competencia o "
    "competidores con ventajas, señales de que el pliego está direccionado a un "
    "proveedor específico, apertura de cuenta o control de la cuenta, condiciones "
    "del acto de apertura, capacidades o experiencia técnica exigida. También "
    "riesgos severos o inusuales de penalización, incumplimiento u operativos "
    "durante la ejecución del contrato (multas atípicas, rescisión atípica). "
    "No incluir certificaciones o documentación exigida para ofertar (son "
    "requisitos de admisibilidad), causales formales de rechazo, garantías, "
    "fechas o plazos como dato, ni criterios de evaluación."
)


def extractor_riesgos(state: GraphState) -> GraphState:
    return run_extractor(
        state=state,
        result_key="riesgos",
        state_field="riesgos",
        status_field="riesgos_status",
        prompt_file_name="riesgos.txt",
        query=_QUERY,
    )
