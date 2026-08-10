from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from analysis.extraction.glossary import build_keyword_query, build_prompt_glossary_block
from analysis.extraction.state import GraphState
from shared.config import get_settings
from shared.ports.azure_openai import get_azure_openai_client
from shared.ports.azure_search import search_hybrid

logger = structlog.get_logger(__name__)

VALID_EXTRACTION_STATUSES = {"success", "partial", "failed", "not_found", "not_applicable"}
BASE_SYSTEM_PROMPT_FILE = "_base_system.txt"
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"

CANONICAL_PROMPT_FILES = {
    BASE_SYSTEM_PROMPT_FILE,
    RESPONSE_BASE_PROMPT_FILE,
    "objeto_alcance.txt",
    "requisitos_admisibilidad.txt",
    "garantias.txt",
    "plazos_clave.txt",
    "criterios_evaluacion.txt",
    "causales_rechazo.txt",
    "anexos_obligatorios.txt",
    "identificacion_procedimiento.txt",
}

CANONICAL_CATEGORY_PROMPT_MAP = {
    "objeto_alcance": "objeto_alcance.txt",
    "requisitos_admisibilidad": "requisitos_admisibilidad.txt",
    "garantias": "garantias.txt",
    "plazos_clave": "plazos_clave.txt",
    "criterios_evaluacion": "criterios_evaluacion.txt",
    "causales_rechazo": "causales_rechazo.txt",
    "anexos_obligatorios": "anexos_obligatorios.txt",
    "identificacion_procedimiento": "identificacion_procedimiento.txt",
}


@lru_cache(maxsize=32)
def _load_prompt(prompt_file_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / prompt_file_name
    return prompt_path.read_text(encoding="utf-8")


def validate_prompt_inventory() -> None:
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    actual_files = {path.name for path in prompts_dir.glob("*.txt")}

    missing = sorted(CANONICAL_PROMPT_FILES - actual_files)
    extras = sorted(actual_files - CANONICAL_PROMPT_FILES)
    if missing or extras:
        details: list[str] = []
        if missing:
            details.append(f"faltan prompts canónicos: {', '.join(missing)}")
        if extras:
            details.append(f"sobran prompts no permitidos: {', '.join(extras)}")
        raise ValueError("Configuración inválida de prompts de extracción: " + " | ".join(details))


def validate_category_prompt_mapping(result_key: str, prompt_file_name: str) -> None:
    expected_prompt = CANONICAL_CATEGORY_PROMPT_MAP.get(result_key)
    if not expected_prompt:
        raise ValueError(
            f"Categoría de extracción no canónica: '{result_key}'. "
            f"Permitidas: {', '.join(sorted(CANONICAL_CATEGORY_PROMPT_MAP))}"
        )

    if prompt_file_name != expected_prompt:
        raise ValueError(
            "Mapeo categoría->prompt inválido: "
            f"{result_key} debe usar '{expected_prompt}', no '{prompt_file_name}'"
        )


def _build_messages(
    *,
    prompt_file_name: str,
    chunks_block: str,
    glossary_block: str,
    root_key: str,
) -> list[tuple[str, str]]:
    system_prompt = (
        _load_prompt(BASE_SYSTEM_PROMPT_FILE)
        .replace("{glossary_terms}", glossary_block or "(sin sinónimos configurados)")
        .replace("{root_key}", root_key)
    )
    user_prompt = (
        _load_prompt(prompt_file_name).replace("{chunks}", chunks_block).replace("{root_key}", root_key)
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
            f"Sección: {chunk.get('section_path', 'general')}, "
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

    if parsed_confidence is None or not (0.0 <= parsed_confidence <= 1.0):
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


_TABLE_CITATION_RE = re.compile(
    r"^\s*Encabezado:\s*(?P<column>.+?)\s*\|\s*Fila:\s*(?P<row>\d+)\s*\|\s*Valor:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)


def _normalize_for_grounding(text: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split()).lower()


def _is_table_citation(citation: str) -> bool:
    return bool(_TABLE_CITATION_RE.match(citation))


def _citation_verified_in_paragraph_chunk(citation: str, chunk: dict[str, Any]) -> bool:
    normalized_citation = _normalize_for_grounding(citation)
    if not normalized_citation:
        return False
    normalized_content = _normalize_for_grounding(chunk.get("content", ""))
    return normalized_citation in normalized_content


def _expand_short_paragraph_citation(
    citation: str,
    candidate_chunks: list[dict[str, Any]],
    *,
    preferred_snippet: str | None = None,
) -> str:
    citation_text = str(citation or "").strip()
    if len(citation_text) >= 40:
        return citation_text

    normalized_citation = _normalize_for_grounding(citation_text)
    if not normalized_citation:
        return citation_text

    preferred_text = str(preferred_snippet or "").strip()
    normalized_preferred = _normalize_for_grounding(preferred_text)

    if len(preferred_text) >= 40 and normalized_preferred:
        for chunk in candidate_chunks:
            if chunk.get("block_type") == "table":
                continue
            normalized_content = _normalize_for_grounding(chunk.get("content", ""))
            if normalized_preferred in normalized_content:
                return preferred_text[:300]
    # Política estricta: no expandir por match de palabra suelta. Si no hay
    # ancla explícita válida, la cita se conserva y el ítem se penaliza luego.
    return citation_text


def _candidate_rescue_snippets(item: dict[str, Any], *, category: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for raw_value in [item.get("texto_original") if category == "plazos_clave" else None, item.get("valor")]:
        snippet = str(raw_value or "").strip()
        if not snippet:
            continue
        if len(snippet) < 40 or len(snippet) > 300:
            continue
        normalized = _normalize_for_grounding(snippet)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(snippet)

    return candidates


def _rescue_paragraph_citation(
    item: dict[str, Any],
    candidate_chunks: list[dict[str, Any]],
    *,
    category: str,
) -> str | None:
    for snippet in _candidate_rescue_snippets(item, category=category):
        if _verify_reference_grounded(snippet, candidate_chunks):
            return snippet[:300]
    return None


def _citation_verified_in_table_chunk(citation: str, chunk: dict[str, Any]) -> bool:
    match = _TABLE_CITATION_RE.match(citation)
    if not match:
        return False

    table_ref = chunk.get("table_ref")
    if not isinstance(table_ref, dict):
        return False

    try:
        row_index = int(match.group("row").strip())
    except ValueError:
        return False
    if int(table_ref.get("row_index") or -1) != row_index:
        return False

    column_raw = match.group("column").strip()
    headers = [str(header) for header in (table_ref.get("headers") or [])]
    content = str(chunk.get("content", ""))
    column_matches = any(_normalize_for_grounding(header) == _normalize_for_grounding(column_raw) for header in headers) or (
        f"{column_raw}:" in content
    )
    if not column_matches:
        return False

    value = _normalize_for_grounding(match.group("value"))
    if not value:
        return False
    return value in _normalize_for_grounding(content)


def _verify_reference_grounded(citation: str, candidate_chunks: list[dict[str, Any]]) -> bool:
    citation_text = str(citation or "").strip()
    if not citation_text:
        return False
    # Contrato estricto v3: cita literal entre 40 y 300 caracteres.
    # Evita validar palabras sueltas que producen anclajes ambiguos en UI.
    if len(citation_text) < 40 or len(citation_text) > 300:
        return False
    if _is_table_citation(citation):
        table_chunks = [chunk for chunk in candidate_chunks if chunk.get("block_type") == "table"]
        return any(_citation_verified_in_table_chunk(citation, chunk) for chunk in table_chunks)
    # Si el LLM devuelve una cita textual "normal" para un dato que cayó en un
    # chunk de tabla (caso frecuente en carátulas), también debe validarse.
    return any(_citation_verified_in_paragraph_chunk(citation, chunk) for chunk in candidate_chunks)


_PROCEDIMIENTO_CON_NUMERO_RE = re.compile(
    r"(?P<tipo>licitaci[oó]n\s+p[úu]blica|licitaci[oó]n\s+privada|contrataci[oó]n\s+directa|concurso\s+de\s+precios|subasta\s+p[úu]blica)\s*"
    r"(?:n[°ºo\.]?\s*)?(?P<numero>[A-Z0-9\-\/.]+)",
    re.IGNORECASE,
)
_EXPEDIENTE_RE = re.compile(r"\bexpediente\b\s*[:\-]?\s*(?P<value>[A-Z0-9][A-Z0-9\-\/.]{4,})", re.IGNORECASE)
_ORGANISMO_RE = re.compile(
    r"\borganismo\b\s*[:\-]?\s*(?P<value>.+?)(?=\bprocedimiento\b|\bobjeto\b|\bpresupuesto\b|\bexpediente\b|$)",
    re.IGNORECASE,
)
_PRESUPUESTO_RE = re.compile(
    r"\bpresupuesto\s+oficial\b\s*[:\-]?\s*(?P<value>.+?)(?=\bexpediente\b|\bprocedimiento\b|\bobjeto\b|$)",
    re.IGNORECASE,
)


def _normalized_identificacion_tipo(raw_tipo: str) -> str:
    text = _normalize_for_grounding(raw_tipo)
    if "organismo" in text:
        return "organismo_convocante"
    if "expediente" in text:
        return "expediente"
    if "numero" in text and "proced" in text:
        return "numero_procedimiento"
    if text in {"procedimiento", "procedimiento_nro", "procedimiento_numero"}:
        return "numero_procedimiento"
    if "tipo" in text and "proced" in text:
        return "tipo_procedimiento"
    if "jurisd" in text:
        return "jurisdiccion"
    if "presupuesto" in text:
        return "presupuesto_oficial"
    return raw_tipo.strip().lower() or "otro"


def _build_context_citation(content: str, start: int, end: int) -> str:
    text = " ".join(str(content or "").split())
    if not text:
        return ""

    left = max(0, start)
    right = min(len(text), end)
    snippet = text[left:right].strip()

    if len(snippet) < 40:
        left = max(0, left - 100)
        right = min(len(text), right + 140)
        snippet = text[left:right].strip()

    return snippet[:300]


def _augment_identificacion_payload(payload: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_tipos = {
        _normalized_identificacion_tipo(str(item.get("tipo", "")))
        for item in payload
        if isinstance(item, dict)
    }

    additions: list[dict[str, Any]] = []

    sorted_chunks = sorted(
        chunks,
        key=lambda chunk: (
            int(chunk.get("page_number", 0) or 0),
            str(chunk.get("document_id", "")),
        ),
    )

    def add_if_missing(tipo: str, valor: str, chunk: dict[str, Any], match_span: tuple[int, int]) -> None:
        canonical_tipo = _normalized_identificacion_tipo(tipo)
        clean_valor = " ".join(str(valor or "").split()).strip(" .;:-")
        if not clean_valor or canonical_tipo in existing_tipos:
            return

        citation = _build_context_citation(str(chunk.get("content", "")), match_span[0], match_span[1])
        if len(citation) < 40:
            citation = " ".join(str(chunk.get("content", "")).split())[:300]
        if len(citation) < 40:
            return

        additions.append(
            {
                "tipo": canonical_tipo,
                "valor": clean_valor,
                "metadata": {},
                "confidence": 0.78,
                "source_references": [
                    {
                        "document_id": str(chunk.get("document_id", "")),
                        "page_number": int(chunk.get("page_number", 0) or 0),
                        "citation": citation,
                    }
                ],
                "extraction_status": "success",
            }
        )
        existing_tipos.add(canonical_tipo)

    for chunk in sorted_chunks:
        content = " ".join(str(chunk.get("content", "")).split())
        if not content:
            continue

        if "organismo_convocante" not in existing_tipos:
            match = _ORGANISMO_RE.search(content)
            if match:
                add_if_missing("organismo_convocante", match.group("value"), chunk, match.span())

        if "expediente" not in existing_tipos:
            match = _EXPEDIENTE_RE.search(content)
            if match:
                add_if_missing("expediente", match.group("value"), chunk, match.span("value"))

        match = _PROCEDIMIENTO_CON_NUMERO_RE.search(content)
        if match:
            if "tipo_procedimiento" not in existing_tipos:
                add_if_missing("tipo_procedimiento", match.group("tipo"), chunk, match.span("tipo"))
            if "numero_procedimiento" not in existing_tipos:
                numero_text = f"{match.group('tipo')} N° {match.group('numero')}"
                add_if_missing("numero_procedimiento", numero_text, chunk, match.span())

        if "presupuesto_oficial" not in existing_tipos:
            match = _PRESUPUESTO_RE.search(content)
            if match:
                add_if_missing("presupuesto_oficial", match.group("value"), chunk, match.span("value"))

    if not additions:
        return payload
    return [*payload, *additions]


def _verify_citation_grounding(
    items: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    category: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Confirma que cada `source_reference` de cada ítem exista de verdad en los
    chunks recuperados (anti-alucinación). Corre dentro de run_extractor porque
    es el único lugar del pipeline que todavía tiene en scope tanto los ítems ya
    parseados como los `chunks` originales pasados al LLM. Sigue el mismo patrón
    de `_warning` + downgrade a "partial" que ya usa `_penalize_unverifiable` en
    graph.py, sin inventar un mecanismo paralelo."""
    chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        key = (str(chunk.get("document_id", "")), int(chunk.get("page_number", 0) or 0))
        chunks_by_doc_page[key].append(chunk)

    total_items = 0
    unverified_items = 0

    for item in items:
        status = str(item.get("extraction_status", ""))
        refs = item.get("source_references") or []
        if status not in {"success", "partial", "not_applicable"} or not refs:
            continue

        total_items += 1
        any_verified = False
        verified_refs: list[dict[str, Any]] = []
        for ref in refs:
            citation = str(ref.get("citation", ""))
            key = (str(ref.get("document_id", "")), int(ref.get("page_number", 0) or 0))
            candidates = chunks_by_doc_page.get(key)
            if not candidates:
                continue
            citation_for_verification = citation
            if len(citation.strip()) < 40 and category == "plazos_clave":
                preferred = str(item.get("texto_original") or "").strip()
                if preferred and _verify_reference_grounded(preferred, candidates):
                    citation_for_verification = preferred

            rescued_citation: str | None = None
            if _verify_reference_grounded(citation_for_verification, candidates):
                any_verified = True
                normalized_ref = dict(ref)
                if not _is_table_citation(citation):
                    preferred_snippet = None
                    if category == "plazos_clave":
                        preferred_snippet = str(item.get("texto_original") or "").strip() or None
                    normalized_ref["citation"] = _expand_short_paragraph_citation(
                        citation_for_verification,
                        candidates,
                        preferred_snippet=preferred_snippet,
                    )
                verified_refs.append(normalized_ref)
                continue

            if not _is_table_citation(citation):
                rescued_citation = _rescue_paragraph_citation(item, candidates, category=category)

            if rescued_citation:
                any_verified = True
                normalized_ref = dict(ref)
                normalized_ref["citation"] = rescued_citation
                verified_refs.append(normalized_ref)

        if verified_refs:
            item["source_references"] = verified_refs

        if not any_verified:
            unverified_items += 1
            item["source_references"] = []
            if status == "success":
                item["extraction_status"] = "partial"
            item["_warning"] = "cita_no_verificada"

    if total_items:
        logger.info(
            "citation_grounding_check",
            correlation_id=correlation_id,
            category=category,
            total_items=total_items,
            unverified_items=unverified_items,
        )

    return items


def run_extractor(
    *,
    state: GraphState,
    result_key: str,
    state_field: str,
    status_field: str,
    prompt_file_name: str,
    query: str,
    is_object_result: bool = False,
) -> GraphState:
    correlation_id = state["correlation_id"]
    analysis_id = state["analysis_id"]
    validate_category_prompt_mapping(result_key, prompt_file_name)
    logger.info(
        "extractor_started",
        correlation_id=correlation_id,
        analysis_id=analysis_id,
        category=result_key,
    )

    delta: GraphState = {}

    try:
        settings = get_settings()
        keyword_query = build_keyword_query(result_key)
        chunks = search_hybrid(
            query=query,
            analysis_id=analysis_id,
            top_k=settings.extraction_top_k,
            keyword_query=keyword_query or None,
            category_filter=result_key,  # Filtrar por categoría target
        )
        chunks = _truncate_to_token_budget(chunks, settings.extraction_max_context_tokens)

        # Logging de distribución de categorías recuperadas
        category_distribution: dict[str, int] = {}
        for chunk in chunks:
            primary = chunk.get("primary_category", "unknown")
            category_distribution[primary] = category_distribution.get(primary, 0) + 1

        # Métrica de pureza: % de chunks que pertenecen a la categoría target
        target_chunks = sum(
            1
            for chunk in chunks
            if chunk.get("primary_category") == result_key
            or result_key in chunk.get("secondary_categories", [])
        )
        purity_rate = target_chunks / len(chunks) if chunks else 0.0

        logger.info(
            "retrieval_metrics",
            correlation_id=correlation_id,
            category=result_key,
            retrieved_chunks=len(chunks),
            category_distribution=category_distribution,
            target_chunks=target_chunks,
            purity_rate=round(purity_rate, 3),
        )

        if not chunks:
            logger.error(
                "extractor_no_chunks_retrieved",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                category=result_key,
                query=query[:160],
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
            glossary_block=build_prompt_glossary_block(result_key),
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
            if result_key == "identificacion_procedimiento":
                payload = _augment_identificacion_payload(payload, chunks)
            delta[state_field] = [_normalize_item(item) for item in payload if isinstance(item, dict)]

        if is_object_result:
            _verify_citation_grounding(
                [delta[state_field]], chunks, category=result_key, correlation_id=correlation_id
            )

            # Detectar contaminación cruzada en objeto
            from analysis.extraction.extractors.validators import detect_cross_contamination

            contaminated = detect_cross_contamination([delta[state_field]], category=result_key)
            if contaminated:
                logger.warning(
                    "cross_contamination_detected",
                    correlation_id=correlation_id,
                    category=result_key,
                    contaminated_count=len(contaminated),
                )

            delta[status_field] = str(delta[state_field].get("extraction_status", "not_found"))
        else:
            _verify_citation_grounding(delta[state_field], chunks, category=result_key, correlation_id=correlation_id)

            # Detectar contaminación cruzada en lista
            from analysis.extraction.extractors.validators import detect_cross_contamination

            contaminated = detect_cross_contamination(delta[state_field], category=result_key)
            if contaminated:
                logger.warning(
                    "cross_contamination_detected",
                    correlation_id=correlation_id,
                    category=result_key,
                    contaminated_count=len(contaminated),
                )

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
