from __future__ import annotations

from collections import defaultdict

import structlog
from langgraph.graph import END, StateGraph

from analysis.extraction.extractors import (
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_cronograma_proceso,
    extractor_documentos_requeridos,
    extractor_estimacion_presupuesto,
    extractor_garantias,
    extractor_plazos,
    extractor_restricciones_participacion,
)
from analysis.extraction.schemas import ExtractedData
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)


def calculate_confidence(source_references: list[dict], extraction_status: str) -> float:
    if extraction_status in {"failed", "not_found"}:
        return 0.0

    confidence = 0.5
    if len(source_references) > 1:
        confidence += 0.3
    elif len(source_references) == 1:
        confidence += 0.2

    if source_references:
        avg_citation_length = sum(len(str(ref.get("citation", ""))) for ref in source_references) / len(source_references)
        if avg_citation_length > 100:
            confidence += 0.2

    return min(confidence, 1.0)


def get_confidence_level(confidence: float) -> str:
    if confidence >= 0.8:
        return "alta"
    if confidence >= 0.6:
        return "media"
    return "baja"


def _normalize_confidence(item: dict) -> dict:
    status = str(item.get("extraction_status", "success"))
    refs = list(item.get("source_references", []))
    if "confidence" not in item:
        item["confidence"] = calculate_confidence(refs, status)
    item["confidence_level"] = get_confidence_level(float(item.get("confidence", 0.0) or 0.0))
    return item


def setup_node(state: GraphState) -> GraphState:
    logger.info("setup_node_started", correlation_id=state["correlation_id"], analysis_id=state["analysis_id"])
    state.update(
        {
            "plazos": [],
            "plazos_status": "pending",
            "garantias": [],
            "garantias_status": "pending",
            "causales": [],
            "causales_status": "pending",
            "documentos": [],
            "documentos_status": "pending",
            "criterios": [],
            "criterios_status": "pending",
            "restricciones": [],
            "restricciones_status": "pending",
            "cronograma": [],
            "cronograma_status": "pending",
            "presupuesto": {},
            "presupuesto_status": "pending",
            "conflicts": [],
        }
    )
    logger.info("setup_node_completed", correlation_id=state["correlation_id"])
    return state


def merge_node(state: GraphState) -> GraphState:
    correlation_id = state["correlation_id"]
    logger.info("merge_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    plazos = [_normalize_confidence(item) for item in state.get("plazos", [])]
    garantias = [_normalize_confidence(item) for item in state.get("garantias", [])]
    causales = [_normalize_confidence(item) for item in state.get("causales", [])]
    documentos = [_normalize_confidence(item) for item in state.get("documentos", [])]
    criterios = [_normalize_confidence(item) for item in state.get("criterios", [])]
    restricciones = [_normalize_confidence(item) for item in state.get("restricciones", [])]
    cronograma = [_normalize_confidence(item) for item in state.get("cronograma", [])]
    presupuesto = _normalize_confidence(dict(state.get("presupuesto", {}))) if state.get("presupuesto") else None

    extracted_data = {
        "plazos": plazos,
        "plazos_extraction_status": state.get("plazos_status", "unknown"),
        "garantias": garantias,
        "garantias_extraction_status": state.get("garantias_status", "unknown"),
        "causales_rechazo": causales,
        "causales_extraction_status": state.get("causales_status", "unknown"),
        "documentos_requeridos": documentos,
        "documentos_extraction_status": state.get("documentos_status", "unknown"),
        "criterios_evaluacion": criterios,
        "criterios_extraction_status": state.get("criterios_status", "unknown"),
        "restricciones_participacion": restricciones,
        "restricciones_extraction_status": state.get("restricciones_status", "unknown"),
        "cronograma_proceso": cronograma,
        "cronograma_extraction_status": state.get("cronograma_status", "unknown"),
        "estimacion_presupuesto": presupuesto,
        "presupuesto_extraction_status": state.get("presupuesto_status", "unknown"),
    }

    token_usage = {
        "plazos": state.get("plazos_token_usage", {}),
        "garantias": state.get("garantias_token_usage", {}),
        "causales": state.get("causales_token_usage", {}),
        "documentos_requeridos": state.get("documentos_token_usage", {}),
        "criterios_evaluacion": state.get("criterios_token_usage", {}),
        "restricciones_participacion": state.get("restricciones_token_usage", {}),
        "cronograma_proceso": state.get("cronograma_token_usage", {}),
        "estimacion_presupuesto": state.get("presupuesto_token_usage", {}),
    }

    conflicts: list[dict] = []

    plazos_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for plazo in plazos:
        plazos_by_tipo[str(plazo.get("tipo", "")).strip().lower()].append(plazo)

    for tipo, items in plazos_by_tipo.items():
        if tipo and len(items) > 1:
            fechas = {item.get("fecha") for item in items}
            if len(fechas) > 1:
                conflicts.append(
                    {
                        "category": "plazos",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Fechas diferentes en distintos documentos",
                    }
                )

    garantias_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for garantia in garantias:
        garantias_by_tipo[str(garantia.get("tipo", "")).strip().lower()].append(garantia)

    for tipo, items in garantias_by_tipo.items():
        if tipo and len(items) > 1:
            montos = {(item.get("monto_porcentaje"), item.get("monto_valor")) for item in items}
            if len(montos) > 1:
                conflicts.append(
                    {
                        "category": "garantias",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Montos diferentes en distintos documentos",
                    }
                )

    validated = ExtractedData(**extracted_data)
    state["extracted_data"] = validated.model_dump()
    state["conflicts"] = conflicts
    state["extraction_metadata"] = {"token_usage": token_usage}

    logger.info(
        "merge_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        conflicts_count=len(conflicts),
    )
    return state


builder = StateGraph(GraphState)

builder.add_node("setup", setup_node)
builder.add_node("extract_plazos", extractor_plazos)
builder.add_node("extract_garantias", extractor_garantias)
builder.add_node("extract_causales", extractor_causales)
builder.add_node("extract_documentos", extractor_documentos_requeridos)
builder.add_node("extract_criterios", extractor_criterios_evaluacion)
builder.add_node("extract_restricciones", extractor_restricciones_participacion)
builder.add_node("extract_cronograma", extractor_cronograma_proceso)
builder.add_node("extract_presupuesto", extractor_estimacion_presupuesto)
builder.add_node("merge", merge_node)

builder.set_entry_point("setup")

extractor_nodes = [
    "extract_plazos",
    "extract_garantias",
    "extract_causales",
    "extract_documentos",
    "extract_criterios",
    "extract_restricciones",
    "extract_cronograma",
    "extract_presupuesto",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", END)

graph = builder.compile()
