from __future__ import annotations

from collections import defaultdict
import unicodedata

import structlog
from langgraph.graph import END, StateGraph

from analysis.extraction.extractors import (
    extractor_anexos_obligatorios,
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_garantias,
    extractor_objeto_alcance,
    extractor_plazos,
    extractor_requisitos_admisibilidad,
)
from analysis.extraction.schemas import ExtractedData
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)


def _merge_category_status(*statuses: str) -> str:
    pool = {str(status or "").strip() for status in statuses}
    if "success" in pool:
        return "success"
    if "partial" in pool:
        return "partial"
    if "not_applicable" in pool:
        return "not_applicable"
    if "not_found" in pool:
        return "not_found"
    if "failed" in pool:
        return "failed"
    return "unknown"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _canonical_plazo_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otro"

    if "respuesta" in text and "consulta" in text:
        return "respuesta_consultas"
    if "consulta" in text:
        return "consultas"
    if "visita" in text and "obra" in text:
        return "visita_obra"
    if "apertura" in text:
        return "apertura"
    if "mantenimiento" in text and "oferta" in text:
        return "mantenimiento_oferta"
    if "adjudic" in text:
        return "adjudicacion"
    if "firma" in text and "contrato" in text:
        return "firma_contrato"
    if "inicio" in text and ("ejecucion" in text or "prestacion" in text):
        return "inicio_ejecucion"
    if "entrega" in text:
        return "entrega"
    if "garantia" in text and "tecnica" in text:
        return "garantia_tecnica"
    if "impugn" in text:
        return "impugnacion"
    if (
        "presentacion de ofertas" in text
        or "cierre de recepcion de ofertas" in text
        or "fecha limite de presentacion" in text
        or ("presentacion" in text and "oferta" in text)
        or ("recepcion" in text and "oferta" in text)
    ):
        return "presentacion_ofertas"
    return "otro"


def _canonical_garantia_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otra"

    if "cumplimiento" in text and "contrato" in text:
        return "cumplimiento_contrato"
    if "anticipo" in text:
        return "anticipo"
    if "impugn" in text:
        return "impugnacion"
    if (
        "mantenimiento" in text
        or "seriedad" in text
        or ("garantia" in text and "oferta" in text)
        or ("caucion" in text and "oferta" in text)
        or ("fianza" in text and "oferta" in text)
    ):
        return "mantenimiento_oferta"
    return "otra"


def calculate_confidence(source_references: list[dict], extraction_status: str) -> float:
    if extraction_status in {"failed", "not_found"}:
        return 0.0

    if extraction_status == "not_applicable":
        return 0.7 if source_references else 0.0

    if not source_references:
        return 0.3

    confidence = 0.5
    if len(source_references) > 1:
        confidence += 0.3
    elif len(source_references) == 1:
        confidence += 0.2

    if source_references:
        avg_citation_length = sum(len(str(ref.get("citation", ""))) for ref in source_references) / len(source_references)
        if avg_citation_length > 100:
            confidence += 0.2
        elif avg_citation_length < 25:
            confidence -= 0.2

    if extraction_status == "partial":
        confidence -= 0.2

    return max(0.0, min(confidence, 1.0))


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


def _penalize_unverifiable(item: dict) -> dict:
    """Marca como partial los items sin citas verificables."""
    refs = list(item.get("source_references", []))
    status = str(item.get("extraction_status", ""))
    if status in {"success", "partial"}:
        usable = [ref for ref in refs if len(str(ref.get("citation", "")).strip()) >= 25]
        if not usable:
            item["extraction_status"] = "partial"
            item["_warning"] = "cita_insuficiente"
    return item


def setup_node(state: GraphState) -> GraphState:
    logger.info("setup_node_started", correlation_id=state["correlation_id"], analysis_id=state["analysis_id"])
    state.update(
        {
            "objeto_alcance": [],
            "objeto_alcance_status": "pending",
            "requisitos_admisibilidad": [],
            "requisitos_admisibilidad_status": "pending",
            "plazos": [],
            "plazos_status": "pending",
            "garantias": [],
            "garantias_status": "pending",
            "causales": [],
            "causales_status": "pending",
            "anexos": [],
            "anexos_status": "pending",
            "criterios": [],
            "criterios_status": "pending",
            "conflicts": [],
        }
    )
    logger.info("setup_node_completed", correlation_id=state["correlation_id"])
    return state


def merge_node(state: GraphState) -> GraphState:
    correlation_id = state["correlation_id"]
    logger.info("merge_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    plazos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("plazos", [])]
    objeto_alcance = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("objeto_alcance", [])]
    requisitos_admisibilidad = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("requisitos_admisibilidad", [])
    ]
    garantias = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("garantias", [])]
    causales = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("causales", [])]
    anexos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("anexos", [])]
    criterios = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("criterios", [])]

    extracted_data = {
        "objeto_alcance": objeto_alcance,
        "objeto_alcance_extraction_status": state.get("objeto_alcance_status", "unknown"),
        "requisitos_admisibilidad": requisitos_admisibilidad,
        "requisitos_admisibilidad_extraction_status": state.get("requisitos_admisibilidad_status", "unknown"),
        "plazos_clave": plazos,
        "plazos_clave_extraction_status": state.get("plazos_status", "unknown"),
        "plazos": plazos,
        "plazos_extraction_status": state.get("plazos_status", "unknown"),
        "garantias": garantias,
        "garantias_extraction_status": state.get("garantias_status", "unknown"),
        "causales_rechazo": causales,
        "causales_extraction_status": state.get("causales_status", "unknown"),
        "anexos_obligatorios": anexos,
        "anexos_extraction_status": state.get("anexos_status", "unknown"),
        "datos_procedimiento": [],
        "datos_procedimiento_extraction_status": "not_found",
        "documentos_requeridos": [],
        "documentos_extraction_status": "not_found",
        "criterios_evaluacion": criterios,
        "criterios_extraction_status": state.get("criterios_status", "unknown"),
        "restricciones_participacion": [],
        "restricciones_extraction_status": "not_found",
        "cronograma_proceso": [],
        "cronograma_extraction_status": "not_found",
        "estimacion_presupuesto": None,
        "presupuesto_extraction_status": "not_found",
    }

    token_usage = {
        "objeto_alcance": state.get("objeto_alcance_token_usage", {}),
        "requisitos_admisibilidad": state.get("requisitos_admisibilidad_token_usage", {}),
        "plazos_clave": state.get("plazos_token_usage", {}),
        "garantias": state.get("garantias_token_usage", {}),
        "causales_rechazo": state.get("causales_token_usage", {}),
        "anexos_obligatorios": state.get("anexos_token_usage", {}),
        "criterios_evaluacion": state.get("criterios_token_usage", {}),
    }

    conflicts: list[dict] = []

    plazos_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for plazo in plazos:
        tipo = _canonical_plazo_tipo(str(plazo.get("tipo", "")))
        plazo["tipo"] = tipo
        plazos_by_tipo[tipo].append(plazo)

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
        tipo = _canonical_garantia_tipo(str(garantia.get("tipo", "")))
        garantia["tipo"] = tipo
        garantias_by_tipo[tipo].append(garantia)

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
builder.add_node("extract_objeto_alcance", extractor_objeto_alcance)
builder.add_node("extract_plazos", extractor_plazos)
builder.add_node("extract_garantias", extractor_garantias)
builder.add_node("extract_causales", extractor_causales)
builder.add_node("extract_anexos", extractor_anexos_obligatorios)
builder.add_node("extract_requisitos", extractor_requisitos_admisibilidad)
builder.add_node("extract_criterios", extractor_criterios_evaluacion)
builder.add_node("merge", merge_node)

builder.set_entry_point("setup")

extractor_nodes = [
    "extract_objeto_alcance",
    "extract_plazos",
    "extract_garantias",
    "extract_causales",
    "extract_anexos",
    "extract_requisitos",
    "extract_criterios",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", END)

graph = builder.compile()
