from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from analysis.extraction.state import GraphState
from shared.ports.azure_openai import get_azure_openai_client
from shared.ports.azure_search import search_hybrid

logger = structlog.get_logger(__name__)


def _load_prompt(prompt_file_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / prompt_file_name
    return prompt_path.read_text(encoding="utf-8")


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""

    return "\n\n".join(
        [
            f"[Documento: {chunk.get('document_id', 'desconocido')}, Página: {chunk.get('page_number', 0)}]\n"
            f"{chunk.get('content', '')}"
            for chunk in chunks
        ]
    )


def _parse_json_response(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(prompt: str, correlation_id: str) -> tuple[dict[str, Any], dict[str, int]]:
    llm = get_azure_openai_client()
    response = llm.invoke(prompt)
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

    normalized["confidence"] = float(normalized.get("confidence", 0.0) or 0.0)
    normalized["source_references"] = list(normalized.get("source_references", []))
    normalized["extraction_status"] = str(normalized.get("extraction_status", "success"))
    return normalized


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
        chunks = search_hybrid(
            query=query,
            analysis_id=analysis_id,
            top_k=10,
            section_key=section_key,
        )
        prompt_template = _load_prompt(prompt_file_name)
        prompt = prompt_template.replace("{chunks}", _format_chunks(chunks))

        llm_result, token_usage = _call_llm(prompt=prompt, correlation_id=correlation_id)
        token_usage_key = f"{state_field}_token_usage"
        delta[token_usage_key] = token_usage

        payload = llm_result.get(result_key)
        if is_object_result:
            if not isinstance(payload, dict):
                payload = _default_not_found_item()
            delta[state_field] = _normalize_item(payload, fallback={"tipo": "estimacion_presupuesto"})
        else:
            if not isinstance(payload, list) or not payload:
                payload = [_default_not_found_item()]
            delta[state_field] = [_normalize_item(item) for item in payload if isinstance(item, dict)]

        has_data = False
        if is_object_result:
            has_data = delta[state_field].get("extraction_status") == "success"
        else:
            has_data = any(item.get("extraction_status") == "success" for item in delta[state_field])

        delta[status_field] = "success" if has_data else "not_found"
        logger.info(
            "extractor_completed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            category=result_key,
            status=delta[status_field],
        )
    except Exception as exc:
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
