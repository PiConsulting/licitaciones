from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from analysis.extraction.glossary import build_prompt_glossary_block, build_query_from_glossary
from analysis.extraction.state import GraphState
from shared.config import get_settings
from shared.ports.azure_openai import get_azure_openai_client
from shared.ports.azure_search import search_hybrid

logger = structlog.get_logger(__name__)

VALID_EXTRACTION_STATUSES = {"success", "partial", "failed", "not_found", "not_applicable"}
BASE_SYSTEM_PROMPT_FILE = "_base_system.txt"
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@lru_cache(maxsize=32)
def _load_prompt(prompt_file_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / prompt_file_name
    return prompt_path.read_text(encoding="utf-8")


def _build_messages(
    *,
    prompt_file_name: str,
    chunks_block: str,
    glossary_block: str,
    root_key: str,
) -> list[tuple[str, str]]:
    system_prompt = (
        _load_prompt(BASE_SYSTEM_PROMPT_FILE)
        .replace("{glossary_terms}", glossary_block or "(sin sinonimos configurados)")
        .replace("{root_key}", root_key)
    )
    user_prompt = (
        _load_prompt(prompt_file_name)
        .replace("{chunks}", chunks_block)
        .replace("{glossary_terms}", glossary_block or "(sin sinonimos configurados)")
        .replace("{root_key}", root_key)
    )
    return [("system", system_prompt), ("human", user_prompt)]


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""

    formatted: list[str] = []
    for position, chunk in enumerate(chunks, start=1):
        header = (
            f"[Fragmento: F{position}, "
            f"Documento: {chunk.get('document_id', 'desconocido')}, "
            f"Página: {chunk.get('page_number', 0)}, "
            f"Sección: {chunk.get('section_path', chunk.get('section_key', 'general'))}, "
            f"Tipo: {'TABLA' if chunk.get('block_type') == 'table' else 'PÁRRAFO'}"
            f"{_table_hint(chunk)}]"
        )
        formatted.append(f"{header}\n{chunk.get('content', '')}")
    return "\n\n".join(formatted)


def _table_hint(chunk: dict[str, Any]) -> str:
    table_ref = chunk.get("table_ref")
    if not isinstance(table_ref, dict):
        return ""
    table_id = table_ref.get("table_id")
    row_index = table_ref.get("row_index")
    if table_id is None or row_index is None:
        return ""
    return f", Tabla: {table_id}, Fila: {row_index}"


def _parse_json_response(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        raise ValueError(f"Respuesta del LLM sin JSON parseable: {raw[:200]}")
    return json.loads(match.group(0))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(messages: list[tuple[str, str]], correlation_id: str) -> tuple[dict[str, Any], dict[str, int]]:
    llm = get_azure_openai_client()

    try:
        bound = llm.bind(response_format={"type": "json_object"})
        response = bound.invoke(messages)
    except Exception:  # noqa: BLE001
        response = llm.invoke(messages)

    parsed = _parse_json_response(str(response.content))

    usage = response.response_metadata.get("token_usage", {}) if hasattr(response, "response_metadata") else {}
    if not usage and hasattr(response, "response_metadata"):
        usage = response.response_metadata.get("usage", {}) or {}

    prompt_tokens = int(
        usage.get("prompt_tokens", usage.get("input_tokens", usage.get("billed_units", {}).get("input_tokens", 0)))
        or 0
    )
    completion_tokens = int(
        usage.get(
            "completion_tokens",
            usage.get("output_tokens", usage.get("billed_units", {}).get("output_tokens", 0)),
        )
        or 0
    )
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)
    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }

    logger.info(
        "extractor_llm_invoked",
        correlation_id=correlation_id,
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
        total_tokens=token_usage["total_tokens"],
    )
    return parsed, token_usage


def _default_not_found_item() -> dict[str, Any]:
    return {
        "tipo": "No encontrado",
        "valor": None,
        "confidence": 0.0,
        "source_references": [],
        "extraction_status": "not_found",
    }


def _normalize_item(item: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = dict(fallback or {})
    normalized.update(item)

    raw_confidence = normalized.get("confidence")
    try:
        parsed_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        parsed_confidence = None

    if parsed_confidence is None or not (0.0 < parsed_confidence <= 1.0):
        normalized.pop("confidence", None)
    else:
        normalized["confidence"] = min(parsed_confidence, 1.0)

    normalized["source_references"] = list(normalized.get("source_references", []))
    status = str(normalized.get("extraction_status", "")).strip()
    if status not in VALID_EXTRACTION_STATUSES:
        logger.warning("invalid_extraction_status", received=status[:80])
        status = "partial" if normalized.get("source_references") else "not_found"
    normalized["extraction_status"] = status
    return normalized


def _truncate_to_token_budget(chunks: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    used = 0
    for chunk in chunks:
        cost = len(str(chunk.get("content", "")).split())
        if used + cost > budget and kept:
            break
        kept.append(chunk)
        used += cost
    return kept


def _aggregate_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("extraction_status", "not_found")) for item in items}
    if "success" in statuses:
        return "success"
    if "partial" in statuses:
        return "partial"
    if "not_applicable" in statuses:
        return "not_applicable"
    if "not_found" in statuses:
        return "not_found"
    if "failed" in statuses:
        return "failed"
    return "not_found"


def run_extractor(
    *,
    state: GraphState,
    result_key: str,
    state_field: str,
    status_field: str,
    prompt_file_name: str,
    query: str,
    section_key: str,
    is_object_result: bool = False,
    glossary_key: str | None = None,
) -> GraphState:
    correlation_id = state["correlation_id"]
    analysis_id = state["analysis_id"]
    logger.info(
        "extractor_started",
        correlation_id=correlation_id,
        analysis_id=analysis_id,
        category=result_key,
    )

    delta: GraphState = {}

    try:
        resolved_glossary_key = glossary_key or result_key
        resolved_query = build_query_from_glossary(resolved_glossary_key, query)
        settings = get_settings()
        chunks = search_hybrid(
            query=resolved_query,
            analysis_id=analysis_id,
            top_k=settings.extraction_top_k,
            section_key=section_key,
        )
        chunks = _truncate_to_token_budget(chunks, settings.extraction_max_context_tokens)

        if not chunks:
            logger.error(
                "extractor_no_chunks_retrieved",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                category=result_key,
                section_key=section_key,
                query=resolved_query[:160],
            )
            delta[state_field] = _default_not_found_item() if is_object_result else []
            delta[status_field] = "not_found"
            delta[f"{state_field}_token_usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            return delta

        messages = _build_messages(
            prompt_file_name=prompt_file_name,
            chunks_block=_format_chunks(chunks),
            glossary_block=build_prompt_glossary_block(resolved_glossary_key),
            root_key=result_key,
        )

        llm_result, token_usage = _call_llm(messages=messages, correlation_id=correlation_id)
        token_usage_key = f"{state_field}_token_usage"
        delta[token_usage_key] = token_usage

        if llm_result.get("_diagnostic") == "sin_contenido_recuperado":
            logger.error(
                "extractor_empty_content_reported_by_llm",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                category=result_key,
            )

        payload = llm_result.get(result_key)
        if is_object_result:
            if not isinstance(payload, dict):
                payload = _default_not_found_item()
            delta[state_field] = _normalize_item(payload, fallback={"tipo": "estimacion_presupuesto"})
        else:
            if not isinstance(payload, list):
                logger.warning("payload_no_es_lista", category=result_key, tipo=type(payload).__name__)
                payload = []
            delta[state_field] = [_normalize_item(item) for item in payload if isinstance(item, dict)]

        if is_object_result:
            delta[status_field] = str(delta[state_field].get("extraction_status", "not_found"))
        else:
            delta[status_field] = _aggregate_status(delta[state_field])
        logger.info(
            "extractor_completed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            category=result_key,
            status=delta[status_field],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "extractor_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            category=result_key,
            error=str(exc),
        )
        delta[state_field] = _default_not_found_item() if is_object_result else []
        delta[status_field] = "failed"

    return delta
