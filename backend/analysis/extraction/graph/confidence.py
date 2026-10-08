"""Calculo de confianza de un item/categoria a partir del status de extraccion y de si sus citas quedaron verificadas."""
from __future__ import annotations

import structlog

from analysis.extraction.schemas import CITATION_MIN_CHARS

logger = structlog.get_logger(__name__)


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
    """La confianza que ve el usuario se CALCULA; no se le pregunta al modelo."""
    status = str(item.get("extraction_status", "success"))
    refs = list(item.get("source_references", []))

    if "confidence" in item:
        try:
            item["confidence_llm"] = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            item["confidence_llm"] = None

    item["confidence"] = calculate_confidence(refs, status)
    item["confidence_level"] = get_confidence_level(float(item.get("confidence", 0.0) or 0.0))
    return item


def _penalize_unverifiable(item: dict) -> dict:
    """Marca como partial los items sin citas utilizables. El piso es el mismo
    `CITATION_MIN_CHARS` que usan el verificador de grounding, el schema y el
    prompt: cuando cada capa tenia su propio umbral, una cita literal y
    verificable sobrevivia al grounding y despues era degradada -- o rechazada
    por pydantic -- solo por su largo, que depende de como redacta cada pliego."""
    refs = list(item.get("source_references", []))
    status = str(item.get("extraction_status", ""))
    if status in {"success", "partial"}:
        usable = [
            ref for ref in refs if len(str(ref.get("citation", "")).strip()) >= CITATION_MIN_CHARS
        ]
        if not usable:
            item["extraction_status"] = "partial"
            item["_warning"] = "cita_insuficiente"
    return item


def _category_confidence(items: list[dict]) -> float:
    """Calcula un score de confianza agregado para toda la categoría."""
    with_confidence = [
        float(item.get("confidence", 0.0) or 0.0)
        for item in items
        if float(item.get("confidence", 0.0) or 0.0) > 0.0
    ]
    if not with_confidence:
        return 0.0
    return round(sum(with_confidence) / len(with_confidence), 2)
