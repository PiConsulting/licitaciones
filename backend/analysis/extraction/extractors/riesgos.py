from __future__ import annotations

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.state import GraphState

_QUERY = (
    "Riesgos comerciales y de participación para el oferente limitados a las 9 dimensiones: "
    "plazos de entrega exigentes o penalizados, mantenimiento de oferta, moneda y tipo de cambio, "
    "forma de pago y cobranza, alta competencia o ventajas de competidores, señales de direccionamiento "
    "del pliego a una marca o proveedor específico, control de la cuenta o apertura obligatoria, "
    "condiciones rígidas de apertura de la oferta, y capacidades o experiencia técnica exigida a validar. "
    "No incluir certificaciones o documentación exigida para ofertar (son requisitos de admisibilidad), "
    "causales formales de rechazo, garantías financieras, fechas como simple dato, ni criterios de evaluación."
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
