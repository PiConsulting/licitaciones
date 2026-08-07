from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.extractors import base as extractors_base
from analysis.extraction.schemas import CategoryNarrative, NarrativeParagraphBlock

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"

# Categorias donde cada item suele ser un hecho discreto (un anexo, un
# requisito) y por lo tanto conviene sesgar la sintesis hacia bullet_list.
CHECKLIST_CATEGORIES = {"anexos_obligatorios", "requisitos_admisibilidad"}

# Categorias que SIEMPRE se responden como un unico parrafo, nunca varios
# bloques ni bullet_list, sin importar cuantos hechos distintos haya (pedido
# explicito: mostrar "una sola respuesta" en vez de una tarjeta por causal).
SINGLE_PARAGRAPH_CATEGORIES = {"causales_rechazo"}

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

_CHECKLIST_HINT = (
    "Esta categoría es de tipo checklist: cada ítem suele ser un hecho discreto (un "
    "anexo). Priorizá `bullet_list` por sobre el párrafo, salvo que en los hechos "
    "haya un único punto para mencionar."
)
_NARRATIVE_HINT = (
    "Esta categoría suele tener una idea central: priorizá `paragraph` salvo que "
    "haya varios hechos independientes que ameriten una lista."
)
_SINGLE_PARAGRAPH_HINT = (
    "Esta categoría SIEMPRE se responde con UN SOLO bloque de tipo `paragraph`, "
    "nunca `bullet_list` ni `table`, sin importar cuántos hechos distintos haya. "
    "Redactá un único párrafo fluido en prosa que mencione todos los hechos "
    "encontrados, enumerándolos dentro de la misma oración si hace falta (ej. "
    "\"El pliego establece que serán causales de rechazo de la oferta: (1) ..., "
    "(2) ... y (3) ...\"). No generes más de un bloque para esta categoría."
)

_USABLE_STATUSES = {"success", "partial", "not_applicable"}
_CONFIDENCE_RANK = {"baja": 0, "media": 1, "alta": 2}


@lru_cache(maxsize=1)
def _load_response_base_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / RESPONSE_BASE_PROMPT_FILE
    return prompt_path.read_text(encoding="utf-8")


def _serialize_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


def _collapse_to_single_paragraph(narrative: CategoryNarrative) -> CategoryNarrative:
    """Backstop: el prompt le pide al LLM un único bloque `paragraph` para las
    categorías de `SINGLE_PARAGRAPH_CATEGORIES`, pero si igual devolvió varios
    bloques (o una lista/tabla), esto los consolida en un solo párrafo — así la
    UI nunca muestra "varias respuestas" sueltas para esa categoría, sin
    depender de que el LLM haya seguido la instrucción al pie de la letra."""
    if len(narrative.blocks) <= 1 and (not narrative.blocks or narrative.blocks[0].type == "paragraph"):
        return narrative

    sentences: list[str] = []
    source_ids: list[int] = []
    worst_confidence = "alta"

    def _consume(text: str, confidence_level: str, ids: list[int]) -> None:
        cleaned = text.strip()
        if cleaned:
            sentences.append(cleaned)
        source_ids.extend(ids)
        nonlocal worst_confidence
        if _CONFIDENCE_RANK[confidence_level] < _CONFIDENCE_RANK[worst_confidence]:
            worst_confidence = confidence_level

    for block in narrative.blocks:
        if block.type == "paragraph":
            _consume(block.text, block.confidence_level, block.source_ids)
        elif block.type == "bullet_list":
            for item in block.items:
                _consume(item.text, item.confidence_level, item.source_ids)
        elif block.type == "table":
            for row in block.rows:
                row_text = " ".join(cell.strip() for cell in row.cells if cell.strip())
                _consume(row_text, row.confidence_level, row.source_ids)

    text = " ".join(sentence if sentence.endswith((".", ";", ":")) else f"{sentence}." for sentence in sentences)
    deduped_ids = sorted(set(source_ids))

    return CategoryNarrative(
        blocks=[NarrativeParagraphBlock(text=text, confidence_level=worst_confidence, source_ids=deduped_ids)],
        sources=narrative.sources,
    )


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
        if category_key in SINGLE_PARAGRAPH_CATEGORIES:
            checklist_hint = _SINGLE_PARAGRAPH_HINT
        elif category_key in CHECKLIST_CATEGORIES:
            checklist_hint = _CHECKLIST_HINT
        else:
            checklist_hint = _NARRATIVE_HINT
        prompt = (
            _load_response_base_prompt()
            .replace("{items_json}", _serialize_items(items))
            .replace("{category_label}", category_label)
            .replace("{checklist_hint}", checklist_hint)
        )

        raw, token_usage = extractors_base._call_llm(messages=[("human", prompt)], correlation_id=correlation_id)
        narrative = CategoryNarrative.model_validate(raw)
        if category_key in SINGLE_PARAGRAPH_CATEGORIES:
            narrative = _collapse_to_single_paragraph(narrative)

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
