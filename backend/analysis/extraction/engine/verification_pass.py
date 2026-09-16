"""2da pasada opt-in (Fase 2 auditoría RAG, arquitectura "dos pasadas"):
audita los ítems YA extraídos por el map-reduce de `base.py` contra las
mismas reglas de la categoría, en un llamado LLM aparte que solo ve la lista
corta de candidatos (no los chunks del pliego). Genérico y reusable por
cualquier categoría vía `get_category_verification_pass` -- las reglas que
aplica son SIEMPRE las del prompt de la categoría (recortadas antes de
`<contexto_pliego>`), nunca un texto duplicado a mano acá.

Por qué una 2da pasada y no más instrucciones en el prompt de extracción: ya
se probó (memoria de la auditoría) que agregar más texto explicativo al
prompt de riesgos no cambió el comportamiento -- la tendencia del modelo a
"completar el patrón" (cualquier cláusula puede sonar a riesgo si se le suma
una consecuencia negativa) es más fuerte que la instrucción en el mismo
llamado que ya está ocupado leyendo texto largo. Separar el juicio de
pertenencia en su propio llamado, con una lista corta y ya consolidada,
saca ese juicio del contexto ruidoso.

Diseño defensivo: el LLM de esta pasada NUNCA reescribe `valor` ni
`source_references` -- solo emite decisiones (mantener/descartar/fusionar)
por `id`. La fusión real la hace `_merge_two_items` (ya existente, usado por
el dedup estructural) sobre los ítems originales, así que las citas nunca se
inventan ni se pierden. Ante una decisión faltante o mal formada, el ítem se
mantiene (fail-open): un fallo de parseo no debe borrar datos reales.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from analysis.extraction.engine.item_merging import _merge_two_items
from analysis.extraction.engine.llm_client import _call_llm
from analysis.extraction.engine.prompts import _load_prompt

logger = structlog.get_logger(__name__)

_VERIFICATION_SYSTEM_PROMPT_FILE = "_verification_pass_system.txt"
_VERIFICATION_USER_PROMPT_FILE = "_verification_pass.txt"
_MAX_CITATION_CHARS = 160
_MAX_CITATIONS_PER_ITEM = 2


def _category_rules_block(prompt_file_name: str) -> str:
    """Recorta el prompt de la categoría a solo sus reglas (todo lo anterior
    a `<contexto_pliego>`), la MISMA fuente de verdad que usa la extracción --
    nunca se copian reglas a mano acá."""
    full_prompt = _load_prompt(prompt_file_name)
    rules, _, _ = full_prompt.partition("<contexto_pliego>")
    return rules.strip()


def _candidate_items_block(items: list[dict[str, Any]]) -> str:
    serializable: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        citations = [
            str(ref.get("citation") or "")[:_MAX_CITATION_CHARS]
            for ref in item.get("source_references") or []
            if isinstance(ref, dict) and ref.get("citation")
        ][:_MAX_CITATIONS_PER_ITEM]
        serializable.append(
            {
                "id": index,
                "tipo": item.get("tipo"),
                "subtipo": item.get("subtipo"),
                "valor": item.get("valor"),
                "extraction_status": item.get("extraction_status"),
                "citas": citations,
            }
        )
    return json.dumps(serializable, ensure_ascii=False, indent=2)


def _build_verification_messages(
    *, prompt_file_name: str, root_key: str, items: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    system_prompt = _load_prompt(_VERIFICATION_SYSTEM_PROMPT_FILE)
    user_prompt = (
        _load_prompt(_VERIFICATION_USER_PROMPT_FILE)
        .replace("{category_rules}", _category_rules_block(prompt_file_name))
        .replace("{root_key}", root_key)
        .replace("{candidate_items}", _candidate_items_block(items))
    )
    return [("system", system_prompt), ("human", user_prompt)]


def _apply_verification_decisions(
    items: list[dict[str, Any]], decisions: list[Any]
) -> list[dict[str, Any]]:
    decisions_by_id: dict[int, dict[str, Any]] = {}
    for raw_decision in decisions or []:
        if not isinstance(raw_decision, dict):
            continue
        try:
            item_id = int(raw_decision.get("id"))
        except (TypeError, ValueError):
            continue
        if 0 <= item_id < len(items):
            decisions_by_id[item_id] = raw_decision

    kept: dict[int, dict[str, Any]] = {}
    pending_merges: list[tuple[int, Any]] = []

    for index, item in enumerate(items):
        decision = decisions_by_id.get(index)
        action = str((decision or {}).get("action") or "keep").strip().lower()
        if decision is None or action not in {"keep", "discard", "merge_with"}:
            # Sin decisión o acción irreconocible: fail-open, se mantiene.
            kept[index] = item
        elif action == "discard":
            continue
        elif action == "merge_with":
            pending_merges.append((index, decision.get("target_id")))
        else:
            kept[index] = item

    for source_id, raw_target_id in pending_merges:
        try:
            target_id = int(raw_target_id)
        except (TypeError, ValueError):
            target_id = None
        source_item = items[source_id]
        if target_id is not None and target_id in kept and target_id != source_id:
            kept[target_id] = _merge_two_items(kept[target_id], source_item)
        else:
            # Target inválido o no sobrevivió: no se pierde el dato, queda
            # como ítem propio en vez de desaparecer silenciosamente.
            kept.setdefault(source_id, source_item)

    return [kept[index] for index in sorted(kept)]


def run_verification_pass(
    items: list[dict[str, Any]],
    *,
    prompt_file_name: str,
    root_key: str,
    correlation_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not items:
        return items, empty_usage

    messages = _build_verification_messages(
        prompt_file_name=prompt_file_name, root_key=root_key, items=items
    )
    try:
        result, token_usage = _call_llm(messages=messages, correlation_id=correlation_id)
    except Exception as exc:  # noqa: BLE001 -- fail-open: la extracción base ya es válida sin esto
        logger.warning(
            "verification_pass_failed",
            correlation_id=correlation_id,
            category=root_key,
            error=str(exc)[:200],
        )
        return items, empty_usage

    decisions = result.get("decisions") if isinstance(result, dict) else None
    if not isinstance(decisions, list):
        logger.warning(
            "verification_pass_malformed_response",
            correlation_id=correlation_id,
            category=root_key,
        )
        return items, token_usage

    filtered = _apply_verification_decisions(items, decisions)
    logger.info(
        "verification_pass_completed",
        correlation_id=correlation_id,
        category=root_key,
        items_before=len(items),
        items_after=len(filtered),
    )
    return filtered, token_usage
