from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.extractors import base as extractors_base
from analysis.extraction.schemas import CategoryNarrative

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"

CATEGORY_LABELS = {
    "objeto_alcance": "Objeto y Alcance",
    "requisitos_admisibilidad": "Requisitos de Admisibilidad",
    "garantias": "Garantías",
    "plazos_clave": "Plazos Clave",
    "criterios_evaluacion": "Criterios de Evaluación",
    "causales_rechazo": "Causales de Rechazo",
    "anexos_obligatorios": "Anexos Obligatorios",
}

# Categorias que se muestran como respuesta narrativa en la UI. Distinto de
# `CANONICAL_CATEGORY_PROMPT_MAP` (que incluye tambien `identificacion_procedimiento`,
# usada solo para el titulo/subtitulo del analisis, nunca como una tarjeta de
# categoria propia) para no gastar una llamada LLM de sintesis en una narrativa
# que el frontend nunca renderiza.
NARRATIVE_CATEGORIES = tuple(CATEGORY_LABELS)

_USABLE_STATUSES = {"success", "partial", "not_applicable"}


@lru_cache(maxsize=1)
def _load_response_base_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / RESPONSE_BASE_PROMPT_FILE
    return prompt_path.read_text(encoding="utf-8")


def _serialize_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
) -> tuple[CategoryNarrative, dict[str, int]] | None:
    """Convierte los items ya extraidos de una categoria en una respuesta de
    experto: bloques en lenguaje natural (parrafo/lista/tabla), nunca metadata
    cruda. Devuelve None si no hay contenido util o si la sintesis falla por
    cualquier motivo (LLM, parseo, validacion) — el llamador (grafo) y el
    frontend ya tienen fallback, asi que una categoria nunca se queda sin
    respuesta por un fallo puntual de este paso."""
    if not items or not _has_usable_content(items):
        return None

    try:
        category_label = CATEGORY_LABELS.get(category_key, category_key)
        prompt = (
            _load_response_base_prompt()
            .replace("{items_json}", _serialize_items(items))
            .replace("{category_label}", category_label)
        )

        raw, token_usage = extractors_base._call_llm(messages=[("human", prompt)], correlation_id=correlation_id)
        narrative = CategoryNarrative.model_validate(raw)

        logger.info(
            "synthesis_completed",
            correlation_id=correlation_id,
            category=category_key,
            blocks=len(narrative.blocks),
            sources=len(narrative.sources),
        )
        return narrative, token_usage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "synthesis_failed",
            correlation_id=correlation_id,
            category=category_key,
            error=str(exc),
        )
        return None
