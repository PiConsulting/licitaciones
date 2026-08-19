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
from analysis.extraction.schemas import (
    CITATION_MAX_CHARS,
    CITATION_MIN_CHARS,
    CITATION_PREFERRED_MIN_CHARS,
)
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
    "_output_schema.txt",
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


def _describe_document(document_id: str, labels: dict[str, dict[str, Any]] | None) -> str:
    """Cómo se nombra la fuente en el encabezado del fragmento (CTX-05).

    Sin etiquetas se devuelve el UUID solo, que es lo que hacía antes de que un
    análisis pudiera tener varios documentos. Con etiquetas se antepone el
    nombre y el rol, porque el modelo necesita saber si está leyendo el pliego o
    un anexo antes de decidir qué hacer cuando dicen cosas distintas.

    El UUID no se saca nunca: el prompt exige copiarlo en
    `source_references[].document_id`, y de ahí sale el resaltado.
    """
    if not document_id:
        return "desconocido"

    datos = (labels or {}).get(document_id)
    if not isinstance(datos, dict):
        return document_id

    nombre = str(datos.get("nombre") or "").strip()
    rol = "PLIEGO PRINCIPAL" if datos.get("es_principal") else "ANEXO"
    if not nombre:
        return f"{rol} ({document_id})"
    return f"{nombre} [{rol}] ({document_id})"


def _format_chunks(
    chunks: list[dict[str, Any]],
    document_labels: dict[str, dict[str, Any]] | None = None,
) -> str:
    if not chunks:
        return ""

    formatted: list[str] = []
    for position, chunk in enumerate(chunks, start=1):
        header = (
            f"[Fragmento: F{position}, "
            f"Documento: {_describe_document(str(chunk.get('document_id') or ''), document_labels)}, "
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

    # `strict=False` tolera caracteres de control crudos dentro de los strings.
    # Las citas son texto copiado literal del pliego, y el texto de un PDF trae
    # los saltos de linea del maquetado ("...el importe de las garantias de\nla
    # contratacion..."). Si el modelo no los escapa, el JSON es invalido y se
    # pierde la categoria entera tras agotar los reintentos -- y que una cita
    # caiga o no sobre un salto de renglon depende de como esta maquetado cada
    # pliego, con lo cual el mismo dato se extrae en un PDF y falla en otro.
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        raise ValueError(f"Respuesta del LLM sin JSON parseable: {raw[:200]}")
    return json.loads(match.group(0), strict=False)


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

    # FIX (2026-08-14): esto era `list(normalized.get("source_references", []))`
    # y reventaba con TypeError si el LLM emitía `"source_references": null` en
    # UN solo item -- cosa que el propio prompt induce ("`not_found` ... sin
    # cita"). La excepción sube hasta el `try` de `run_extractor`, que escribe
    # la categoría ENTERA como `failed` con lista vacía. Un item mal formado no
    # puede costar las 30 afirmaciones de la categoría.
    raw_refs = normalized.get("source_references")
    normalized["source_references"] = [ref for ref in raw_refs if isinstance(ref, dict)] if isinstance(raw_refs, list) else []
    status = str(normalized.get("extraction_status", "")).strip()
    if status not in VALID_EXTRACTION_STATUSES:
        logger.warning("invalid_extraction_status", received=status[:80])
        status = "partial" if normalized.get("source_references") else "not_found"
    normalized["extraction_status"] = status
    return normalized


def _item_has_substantive_content(item: dict[str, Any]) -> bool:
    """Detecta si un ítem aporta dato útil más allá del status declarado."""
    text_fields = ("valor", "texto_original", "expresion_relativa", "fecha", "hora", "lugar")
    for field_name in text_fields:
        value = item.get(field_name)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned and cleaned not in {"no encontrado", "not_found"}:
                return True
            continue
        return True

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for meta_value in metadata.values():
            if meta_value is None:
                continue
            if isinstance(meta_value, str):
                cleaned = meta_value.strip().lower()
                if cleaned and cleaned not in {"no_especificado", "no encontrado", "not_found"}:
                    return True
                continue
            return True

    return bool(item.get("source_references"))


def _normalize_mixed_not_found_items(items: list[dict[str, Any]], *, category: str) -> list[dict[str, Any]]:
    """Evita `not_found` a nivel ítem cuando la categoría sí tiene hallazgos.

    Regla pedida por producto: `not_found` solo corresponde cuando la categoría
    completa no encontró nada útil.
    """
    if not items:
        return items

    has_category_findings = any(
        str(item.get("extraction_status", "")).strip() in {"success", "partial", "not_applicable"}
        or _item_has_substantive_content(item)
        for item in items
    )
    if not has_category_findings:
        return items

    normalized_items: list[dict[str, Any]] = []
    converted = 0
    dropped = 0

    for item in items:
        status = str(item.get("extraction_status", "")).strip()
        if status != "not_found":
            normalized_items.append(item)
            continue

        if _item_has_substantive_content(item):
            adjusted = dict(item)
            adjusted["extraction_status"] = "partial"
            normalized_items.append(adjusted)
            converted += 1
        else:
            dropped += 1

    if converted or dropped:
        logger.info(
            "normalized_mixed_not_found_items",
            category=category,
            original_count=len(items),
            kept_count=len(normalized_items),
            converted_to_partial=converted,
            dropped_placeholders=dropped,
        )

    return normalized_items


@lru_cache(maxsize=1)
def _get_token_encoder() -> Any:
    """Encoder de tiktoken para medir el contexto con el tokenizer real del
    modelo (hallazgo M-3: antes se aproximaba con `len(content.split())`,
    que subestima/sobreestima según el idioma -- el español con acentos y
    términos legales tokeniza distinto que el inglés).

    `azure_openai_chat_deployment` es un NOMBRE DE DEPLOYMENT elegido por el
    org (no necesariamente un nombre de modelo de OpenAI), así que no se
    puede asumir que tiktoken lo reconozca. Se prueba en orden: el nombre de
    deployment configurado (por si coincide con un modelo real), el modelo
    real que usa este proyecto en producción (gpt-4o-mini, ver el cálculo de
    costos en `extraction/runner.py`), y como último recurso el encoding
    o200k_base directamente (el que usan los modelos gpt-4o/gpt-4o-mini).

    Devuelve `None` si nada de esto funciona (p.ej. sin conectividad al host
    que sirve el archivo de encoding la primera vez) -- el caller cae
    entonces al conteo aproximado por palabras en vez de crashear la
    extracción completa por un problema de tokenizer.
    """
    try:
        import tiktoken
    except ImportError:
        logger.warning("tiktoken_not_installed")
        return None

    settings = get_settings()
    deployment = (getattr(settings, "azure_openai_chat_deployment", "") or "").strip()
    for candidate in (deployment, "gpt-4o-mini"):
        if not candidate:
            continue
        try:
            return tiktoken.encoding_for_model(candidate)
        except KeyError:
            continue
        except Exception as exc:  # noqa: BLE001 - defensivo, no debe tumbar la extracción
            logger.warning("token_encoder_load_failed", model=candidate, error=str(exc)[:200])
            return None

    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception as exc:  # noqa: BLE001
        logger.warning("token_encoder_fallback_failed", error=str(exc)[:200])
        return None


def _count_tokens(text: str) -> int:
    """Cuenta tokens con el tokenizer real cuando está disponible; si no,
    cae a la aproximación anterior por palabras (nunca lanza)."""
    encoder = _get_token_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception as exc:  # noqa: BLE001
            logger.warning("token_count_failed", error=str(exc)[:200])
    return len(text.split())


# CTX-02: cuántos chunks entran al prompt sí o sí, sin mirar el score. Es el
# piso que impide que un corte por relevancia se lleve evidencia real cuando
# toda la categoría tiene scores parejos y bajos.
_RELEVANCE_MIN_CHUNKS = 10
# Y por debajo de qué fracción del mejor score se descarta el resto. Relativo y
# no absoluto porque los scores de RRF no son comparables entre consultas.
_RELEVANCE_MIN_RATIO = 0.4


def _drop_low_relevance_chunks(
    chunks: list[dict[str, Any]],
    *,
    correlation_id: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Saca la cola de chunks que el retrieval trajo por completar el `top_k`.

    FIX (auditoría 2026-08-13, hallazgo CTX-02): se recuperaban `category_top_k`
    chunks y sólo se recortaban por presupuesto de tokens. No había ningún corte
    por relevancia, así que el chunk en la posición 35 —con un score de RRF
    típicamente la mitad del primero— entraba al prompt con el mismo peso visual
    que el primero.

    Dónde duele: una categoría que en ESE pliego no tiene evidencia real (por
    ejemplo `criterios_evaluacion` en un pliego que adjudica por menor precio,
    sin matriz de puntajes) igual llenaba sus 25-35 chunks con secciones
    tangenciales. Al modelo se le pide ser "un analista experto que reconoce el
    concepto aunque el vocabulario cambie", y después se le da mucho material
    del cual construir un criterio que el pliego no tiene. La instrucción de no
    inventar está; la presión del contexto va en contra.

    El corte es deliberadamente tímido, porque el error caro es el inverso:
    descartar el chunk que sí tenía el dato reproduce exactamente la falla que
    esta auditoría viene persiguiendo (una categoría respondiendo "no
    encontrado" sobre un pliego que sí lo dice). Por eso los primeros
    `_RELEVANCE_MIN_CHUNKS` entran siempre, y un chunk sin score no se juzga.
    """
    if len(chunks) <= _RELEVANCE_MIN_CHUNKS:
        return chunks

    def score_de(chunk: dict[str, Any]) -> float | None:
        valor = chunk.get("search_score")
        try:
            numero = float(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return numero if numero > 0 else None

    scores = [score_de(chunk) for chunk in chunks]
    conocidos = [s for s in scores if s is not None]
    if not conocidos:
        # Mocks y fuentes legacy no traen `search_score`. Sin score no hay
        # criterio, y no tenerlo no puede costar chunks.
        return chunks

    umbral = max(conocidos) * _RELEVANCE_MIN_RATIO
    # El piso se cuenta por score, no por posición: la expansión
    # children→parent puede alterar el orden de la lista.
    protegidos = {
        indice
        for indice, _score in sorted(
            enumerate(scores),
            key=lambda par: (par[1] is None, -(par[1] or 0.0)),
        )[:_RELEVANCE_MIN_CHUNKS]
    }

    conservados: list[dict[str, Any]] = []
    descartados: list[float] = []
    for indice, chunk in enumerate(chunks):
        score = scores[indice]
        if indice in protegidos or score is None or score >= umbral:
            conservados.append(chunk)
        else:
            descartados.append(score)

    if descartados:
        logger.info(
            "extraction_chunks_dropped_low_relevance",
            correlation_id=correlation_id,
            category=category,
            chunks_kept=len(conservados),
            chunks_dropped=len(descartados),
            score_max=round(max(conocidos), 5),
            score_umbral=round(umbral, 5),
            score_descartado_max=round(max(descartados), 5),
        )
    return conservados


def _truncate_to_token_budget(
    chunks: list[dict[str, Any]],
    budget: int,
    *,
    correlation_id: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Recorta la lista de chunks (ya ordenada por relevancia) para que quepa
    en `budget` tokens. FIX (2026-08-13): antes el descarte era completamente
    silencioso -- un pliego con muchos hechos relevantes para una categoría
    (ej. `plazos_clave` con muchos hitos, o `garantias` con varias cláusulas)
    podía perder chunks retrievados-como-relevantes sin ningún rastro, lo que
    hacía indistinguible "el pliego no menciona esto" de "el dato estaba en un
    chunk que no entró en el presupuesto de tokens". Ahora se loguea cuántos
    chunks y qué % del total recuperado se descartó, para cualquier categoría
    y cualquier pliego -- no es una excepción para este caso puntual."""
    kept: list[dict[str, Any]] = []
    used = 0
    dropped = 0
    for index, chunk in enumerate(chunks):
        cost = _count_tokens(str(chunk.get("content", "")))
        if used + cost > budget and kept:
            dropped = len(chunks) - index
            break
        kept.append(chunk)
        used += cost
    if dropped:
        logger.warning(
            "extraction_chunks_dropped_token_budget",
            correlation_id=correlation_id,
            category=category,
            budget=budget,
            tokens_used=used,
            chunks_kept=len(kept),
            chunks_dropped=dropped,
            chunks_retrieved=len(chunks),
        )
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
    if len(citation_text) >= CITATION_PREFERRED_MIN_CHARS:
        return citation_text

    normalized_citation = _normalize_for_grounding(citation_text)
    if not normalized_citation:
        return citation_text

    preferred_text = str(preferred_snippet or "").strip()
    normalized_preferred = _normalize_for_grounding(preferred_text)

    if len(preferred_text) >= CITATION_PREFERRED_MIN_CHARS and normalized_preferred:
        for chunk in candidate_chunks:
            if chunk.get("block_type") == "table":
                continue
            normalized_content = _normalize_for_grounding(chunk.get("content", ""))
            if normalized_preferred in normalized_content:
                return clip_citation(preferred_text)
    # Política estricta: no expandir por match de palabra suelta. Si no hay
    # ancla explícita válida, la cita se conserva y el ítem se penaliza luego.
    return citation_text


def _widen_citation_with_chunk_context(
    citation: str,
    candidate_chunks: list[dict[str, Any]],
    *,
    target_chars: int = CITATION_PREFERRED_MIN_CHARS,
) -> str:
    """Ensancha una cita ya verificada usando el texto que la rodea en el chunk
    donde matcheó, hasta que sea evidencia legible por sí sola.

    El resultado se recorta del contenido real del chunk, así que sigue siendo
    literal y vuelve a verificar sin problemas. Si no se puede ubicar la cita en
    ningún chunk, se devuelve tal cual: ensanchar es una mejora de calidad de la
    evidencia, nunca una condición para conservarla."""
    collapsed_citation = " ".join(str(citation or "").split())
    if not collapsed_citation or len(collapsed_citation) >= target_chars:
        return citation

    needle = collapsed_citation.lower()
    for chunk in candidate_chunks:
        if chunk.get("block_type") == "table":
            continue
        content = " ".join(str(chunk.get("content", "")).split())
        start = content.lower().find(needle)
        if start < 0:
            continue
        widened = _build_context_citation(
            content, start, start + len(collapsed_citation), min_chars=target_chars
        )
        # ATR-07: ensanchar es agregarle contexto a la cita, no cambiarla por
        # otra. Si el resultado ya no contiene lo que el modelo citó, la mejora
        # falló y se devuelve la cita original -- corta pero fiel.
        if len(widened) > len(collapsed_citation) and needle in widened.lower():
            return widened
    return citation


def _candidate_rescue_snippets(item: dict[str, Any], *, category: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for raw_value in [item.get("texto_original") if category == "plazos_clave" else None, item.get("valor")]:
        snippet = str(raw_value or "").strip()
        if not snippet:
            continue
        if len(snippet) < CITATION_MIN_CHARS:
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
            return clip_citation(snippet)
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


def clip_citation(citation: str, max_chars: int = CITATION_MAX_CHARS) -> str:
    """Recorta una cita ya verificada al límite de almacenamiento, cortando en
    un borde de palabra. El recorte preserva el carácter literal de la cita: un
    prefijo de un texto que existe literalmente en el chunk sigue existiendo
    literalmente en el chunk, así que la cita recortada se vuelve a verificar
    igual de bien si el grounding corre otra vez sobre el dato persistido."""
    text = str(citation or "").strip()
    if len(text) <= max_chars:
        return text

    clipped = text[:max_chars]
    last_space = clipped.rfind(" ")
    # Solo cortamos en el último espacio si eso no destruye la cita (nos
    # quedaría por debajo del mínimo discriminante).
    if last_space >= CITATION_MIN_CHARS:
        clipped = clipped[:last_space]
    return clipped.strip()


_DIGITS_RE = re.compile(r"\d[\d.,]*")
# Cuánto texto de arranque se conserva antes del dato al recortar una cita larga.
# Sin nada de lead-in la cita empieza en mitad de una frase y no se entiende;
# con demasiado, el dato queda fuera de la ventana.
_CITATION_LEAD_IN_CHARS = 45


_MILES_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DECIMAL_RE = re.compile(r"^\d+[.,]\d+$")


def _canonical_number(token: str) -> str:
    """Forma canónica de un número escrito de cualquiera de las maneras en que
    aparece entre el pliego y el dato extraído.

    "AR$ 12.000.000" -> "12000000" <- "12000000.0 ARS"

    Los separadores de miles y los decimales nulos son ruido de formato: sin
    normalizarlos, el monto del item nunca matchea el monto de la cita.
    """
    text = str(token or "").strip().strip(".,")
    if _MILES_RE.match(text):
        return text.replace(".", "").replace(",", "")
    if _DECIMAL_RE.match(text):
        entera, _, decimal = text.replace(",", ".").partition(".")
        decimal = decimal.rstrip("0")
        return entera + decimal
    return "".join(ch for ch in text if ch.isdigit())


def _citation_anchor_position(citation: str, item: dict[str, Any]) -> int | None:
    """Dónde, dentro de la cita, está el dato que el item afirma.

    Se prueban tres anclas, de la más fuerte a la más débil:
      1. el `valor` como PALABRA COMPLETA (sin acentos, sin distinguir
         mayúsculas). La palabra completa importa: `valor="Municipal"` matchea
         como subcadena dentro de "Municipalidad" -- que suele estar al
         principio del texto, en el nombre del organismo -- y esa coincidencia
         apuntaría a cualquier lado menos a "Jurisdicción: Municipal";
      2. el `valor` como subcadena, para valores largos (un `causal_rechazo` o
         un `resumen_objeto` son frases enteras que rara vez están literales);
      3. si el valor tiene dígitos, el número, comparado en forma canónica.

    Devuelve None si no se puede ubicar: ahí el recorte cae al prefijo, que es
    el comportamiento de siempre.
    """
    valor = " ".join(str(item.get("valor") or "").split()).strip(" .;:-")
    if not valor:
        return None

    haystack = _normalize_for_grounding(citation)
    if not haystack:
        return None

    needle = _normalize_for_grounding(valor)

    if len(needle) >= 4:
        palabra_completa = re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])", haystack)
        if palabra_completa:
            return palabra_completa.start()

    for candidate in (needle, needle[:40]):
        if len(candidate) >= 12:
            position = haystack.find(candidate)
            if position >= 0:
                return position

    valor_number = _canonical_number(valor.split()[0] if valor.split() else "")
    if len(valor_number) >= 3:
        for match in _DIGITS_RE.finditer(citation):
            if _canonical_number(match.group(0)) == valor_number:
                return match.start()

    return None


def shorten_citation_to_evidence(
    citation: str, item: dict[str, Any], *, max_chars: int = CITATION_MAX_CHARS
) -> str:
    """Recorta una cita larga a la ventana que CONTIENE el dato del item.

    `clip_citation` recorta desde el principio, y eso funciona sólo si el dato
    está en los primeros `max_chars` caracteres. Medido sobre un análisis real,
    no lo está: la carátula de un pliego es un bloque de ~210 caracteres que
    respalda tres items distintos, y tanto "Presupuesto oficial: AR$ 12.000.000"
    como "Jurisdicción: Municipal" caen DESPUÉS del carácter 120. Un prefijo
    dejaría a esos dos items citando un texto que no prueba nada de lo que
    afirman.

    El resultado es siempre una subcadena CONTIGUA y literal de la cita
    original, así que sigue verificando contra el chunk y sigue siendo
    localizable en el PDF por `search_for` -- que es de lo que depende el
    resaltado.
    """
    text = " ".join(str(citation or "").split())
    if len(text) <= max_chars:
        return text

    anchor = _citation_anchor_position(text, item)
    if anchor is None:
        return clip_citation(text, max_chars=max_chars)

    start = max(0, anchor - _CITATION_LEAD_IN_CHARS)
    end = start + max_chars
    if end > len(text):
        start = max(0, len(text) - max_chars)
        end = len(text)

    # Bordes de palabra: nunca partir una palabra al medio, ni al principio ni
    # al final. Si el ajuste dejara la cita por debajo del mínimo, se prefiere
    # el corte crudo antes que perder la cita.
    if start > 0:
        space = text.find(" ", start)
        if 0 <= space < end - CITATION_MIN_CHARS:
            start = space + 1
    if end < len(text):
        space = text.rfind(" ", start, end)
        if space > start + CITATION_MIN_CHARS:
            end = space

    return text[start:end].strip()


def _find_grounding_chunk(
    citation: str, candidate_chunks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Devuelve EL chunk que respalda la cita, o None si ninguno la contiene.

    FIX (auditoría 2026-08-13, hallazgo ATR-01): antes esto era un `any(...)`
    que devolvía sólo un booleano. El código sabía perfectamente cuál de los
    chunks candidatos había matcheado -- lo estaba iterando -- pero descartaba
    esa información, y el `id` del chunk ya venía disponible desde
    `shared/ports/azure_search.py::_document_to_chunk`.

    Consecuencia de tirarlo: todo aguas abajo tenía que RECONSTRUIR la
    identidad del chunk buscando el texto de la cita de nuevo, primero en
    `synthesis._resolve_from_evidence` y después en
    `highlight.compute_highlights_for_sources`. Dos reconstrucciones frágiles
    y costosas de un dato que se tenía gratis. Y como el matcheo aguas arriba
    era por `(document_id, page_number)`, una frase que aparece en dos chunks
    de la misma página (fórmulas jurídicas tipo "conforme lo establecido en el
    presente pliego") podía resolverse al chunk equivocado: el usuario clickea
    un dato de garantías y aterriza en adjudicación.
    """
    citation_text = str(citation or "").strip()
    if not citation_text:
        return None
    # La longitud NO es el criterio de validez: lo es que el texto exista
    # literalmente en un chunk recuperado (ver `CITATION_MIN_CHARS`). El único
    # piso que queda descarta citas demasiado cortas para ser discriminantes
    # ("oferta", "garantía"), que harían match en cualquier chunk. No hay techo:
    # una cita larga es *más* específica, no menos verificable -- se recorta al
    # persistir con `clip_citation`, nunca se descarta.
    if len(citation_text) < CITATION_MIN_CHARS:
        return None

    if _is_table_citation(citation):
        for chunk in candidate_chunks:
            if chunk.get("block_type") != "table":
                continue
            if _citation_verified_in_table_chunk(citation, chunk):
                return chunk
        return None

    # Si el LLM devuelve una cita textual "normal" para un dato que cayó en un
    # chunk de tabla (caso frecuente en carátulas), también debe validarse.
    for chunk in candidate_chunks:
        if _citation_verified_in_paragraph_chunk(citation, chunk):
            return chunk
    return None


def _verify_reference_grounded(citation: str, candidate_chunks: list[dict[str, Any]]) -> bool:
    """Igual que `_find_grounding_chunk` pero en booleano, para los llamadores
    que sólo necesitan saber si la cita se sostiene."""
    return _find_grounding_chunk(citation, candidate_chunks) is not None


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
    # FIX (2026-08-13): "apertura" y "lugar" son campos de carátula tan
    # comunes como "expediente"/"procedimiento"/"objeto" -- sin ellos como
    # tope, un pliego con esos campos justo después del presupuesto (patrón
    # frecuente en carátulas argentinas) hacía que la captura se comiera
    # todo lo que sigue hasta el próximo tope real o el final del texto.
    r"\bpresupuesto\s+oficial\b\s*[:\-]?\s*(?P<value>.+?)"
    r"(?=\bexpediente\b|\bprocedimiento\b|\bobjeto\b|\bapertura\b|\blugar\b|$)",
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


def _word_start(text: str, index: int) -> int:
    """Inicio de la palabra que contiene `index`. Expande hacia afuera."""
    index = max(0, min(index, len(text)))
    while index > 0 and not text[index - 1].isspace():
        index -= 1
    return index


def _word_end(text: str, index: int) -> int:
    """Fin (exclusivo) de la palabra que contiene `index - 1`. Expande hacia afuera."""
    index = max(0, min(index, len(text)))
    while index < len(text) and not text[index].isspace():
        index += 1
    return index


def _build_context_citation(
    content: str,
    start: int,
    end: int,
    *,
    min_chars: int = CITATION_MIN_CHARS,
    max_chars: int = CITATION_MAX_CHARS,
) -> str:
    """Ensancha `content[start:end]` con el texto que lo rodea, sin perderlo.

    FIX (auditoría 2026-08-14, hallazgo ATR-07): la versión anterior ensanchaba
    con dos constantes ciegas -- 100 caracteres a la izquierda y 140 a la
    derecha -- y después llamaba a `clip_citation`, que recorta un PREFIJO. Con
    un núcleo de 33 caracteres eso da una ventana de 273 que arranca 100 antes
    del dato; el prefijo de 120 se queda con los primeros 120 de esa ventana y
    el núcleo, que vivía en el offset 100, quedaba cortado por la mitad o
    directamente afuera.

    Visto en un análisis real (`objeto_alcance`, fuente 3):

        citation_llm : "Item 3: 4 (cuatro) LCD KVM Switch"
        citation     : "m 1: 4 (cuatro) Servidores de aplicaciones tipo XEN
                        Item 2: 4 (cuatro) Servidores de base de datos.
                        Item 3: 4 (cuatro)"

    La cita mostrada arranca en mitad de la palabra "Item", enumera dos ítems
    que no tienen nada que ver con el dato, y NO contiene "LCD KVM Switch" --
    es decir, la evidencia que se le muestra a la persona ya no menciona lo que
    el item afirma. El resaltado la sigue fielmente y marca tres renglones
    equivocados.

    Dos invariantes ahora:
      1. el resultado SIEMPRE contiene `content[start:end]` (salvo que el
         núcleo solo ya no entre en `max_chars`, en cuyo caso se recorta ÉL --
         nunca se lo reemplaza por texto vecino);
      2. los dos bordes caen en límite de palabra.
    """
    text = " ".join(str(content or "").split())
    if not text:
        return ""

    core_start = max(0, min(int(start), len(text)))
    core_end = max(core_start, min(int(end), len(text)))
    core_len = core_end - core_start

    # El núcleo es la evidencia. Si por sí solo excede el techo, se recorta el
    # núcleo: seguimos dentro del texto que respalda el dato.
    if core_len >= max_chars:
        return clip_citation(text[core_start:core_end], max_chars=max_chars)

    # Presupuesto de contexto: lo justo para llegar al mínimo legible, no 240
    # caracteres. Un tercio antes del dato y el resto después -- la persona
    # necesita saber de qué se está hablando, pero el dato tiene que quedar
    # cerca del principio para que se lea como evidencia y no como párrafo.
    budget = max(0, min(max_chars, max(min_chars, core_len)) - core_len)
    lead = budget // 3

    left = _word_start(text, max(0, core_start - lead))
    right = _word_end(text, min(len(text), core_end + (budget - lead)))

    # El redondeo a palabra entera puede pasarse del techo: se devuelve
    # contexto, primero el de la derecha y después el de la izquierda, hasta
    # entrar. El núcleo nunca se toca en este lazo.
    while right - left > max_chars and right > core_end:
        space = text.rfind(" ", core_end, right)
        if space < 0:
            break
        right = space
    while right - left > max_chars and left < core_start:
        space = text.find(" ", left, core_start)
        if space < 0:
            break
        left = space + 1

    snippet = text[left:right].strip()
    return snippet if len(snippet) <= max_chars else clip_citation(snippet, max_chars=max_chars)


# FIX (2026-08-13): estos tres tipos son siempre códigos o montos -- un
# número de procedimiento, un expediente y un presupuesto oficial contienen
# SIEMPRE al menos un dígito en cualquier pliego real. `_PROCEDIMIENTO_CON_NUMERO_RE`
# tiene el grupo "N°" opcional (para reconocer "Licitación Pública 12/2026"
# sin la sigla), lo que significa que sin este chequeo el regex también
# matchea la primera palabra que siga al tipo de procedimiento aunque no sea
# un número en absoluto -- bug real detectado: sobre "Licitación Privada para
# la 'Adquisición de...'" (sin ningún número en el pliego), el regex capturó
# "para" como si fuera el número, dando `valor: "Licitación Privada N° para"`.
# `_PRESUPUESTO_RE` tiene el mismo problema de fondo: sin un tope de
# oración, sobre "PRESUPUESTO OFICIAL: $ X APERTURA: LUGAR: ..." (un pliego
# con el monto real aún sin completar) capturaba toda la frase siguiente como
# si fuera el presupuesto. Este chequeo es la red de seguridad genérica para
# ambos casos -- y para cualquier pliego con la misma estructura, no solo
# este -- sin necesidad de mantener los regex perfectamente anclados.
_TIPOS_IDENTIFICACION_QUE_REQUIEREN_DIGITO = {"numero_procedimiento", "expediente", "presupuesto_oficial"}


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
        if canonical_tipo in _TIPOS_IDENTIFICACION_QUE_REQUIEREN_DIGITO and not any(
            ch.isdigit() for ch in clean_valor
        ):
            logger.debug(
                "identificacion_augment_rejected_no_digit",
                tipo=canonical_tipo,
                valor_descartado=clean_valor[:80],
            )
            return

        citation = _build_context_citation(str(chunk.get("content", "")), match_span[0], match_span[1])
        if len(citation) < CITATION_MIN_CHARS:
            citation = clip_citation(" ".join(str(chunk.get("content", "")).split()))
        if len(citation) < CITATION_MIN_CHARS:
            return

        # Extraer block_id del chunk (de source.blocks o merged_blocks)
        block_id = None
        source_data = chunk.get("source", {})
        if isinstance(source_data, dict):
            blocks = source_data.get("blocks", [])
            if blocks and isinstance(blocks, list) and blocks[0]:
                block_id = str(blocks[0].get("block_id") or blocks[0].get("para_id", ""))
        
        if not block_id:
            # Fallback: usar para_id directo del chunk (formato legacy)
            block_id = str(chunk.get("para_id", "")) if chunk.get("para_id") else None
        
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
                        "block_id": block_id,
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


def _as_page_number(value: Any) -> int:
    """El número de página de una referencia, tolerando lo que emita el LLM.

    "3" -> 3 | 3 -> 3 | "3-4" -> 3 | "pág. 12" -> 12 | "s/n" -> 0
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


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
    rescued_items = 0

    for item in items:
        status = str(item.get("extraction_status", ""))
        refs = item.get("source_references") or []
        if status not in {"success", "partial", "not_applicable"} or not refs:
            continue

        total_items += 1
        any_verified = False
        rescued_refs_count = 0
        verified_refs: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            citation = str(ref.get("citation", ""))
            # FIX (2026-08-14): `int(...)` directo reventaba con ValueError ante
            # un `page_number` que el LLM escribiera como "3-4", "12 y 13" o
            # "s/n" -- formas que aparecen cuando una cita cruza dos páginas del
            # pliego. Igual que arriba: un ref raro degrada ese ref, no la
            # categoría entera.
            key = (str(ref.get("document_id", "")), _as_page_number(ref.get("page_number")))
            candidates = chunks_by_doc_page.get(key)
            if not candidates:
                continue
            citation_for_verification = citation
            if len(citation.strip()) < CITATION_MIN_CHARS and category == "plazos_clave":
                preferred = str(item.get("texto_original") or "").strip()
                if preferred and _verify_reference_grounded(preferred, candidates):
                    citation_for_verification = preferred

            rescued_citation: str | None = None
            grounding_chunk = _find_grounding_chunk(citation_for_verification, candidates)
            if grounding_chunk is not None:
                any_verified = True
                normalized_ref = dict(ref)
                # ATR-01: se registra QUÉ chunk respaldó la cita. Es el eslabón
                # que faltaba entre "retrieved chunk" y "used evidence": sin
                # esto, síntesis y highlighting tienen que volver a buscar el
                # texto para adivinar de qué chunk salió.
                _attach_chunk_identity(normalized_ref, grounding_chunk)
                final_citation = citation_for_verification
                if not _is_table_citation(citation):
                    preferred_snippet = None
                    if category == "plazos_clave":
                        preferred_snippet = str(item.get("texto_original") or "").strip() or None
                    final_citation = _expand_short_paragraph_citation(
                        citation_for_verification,
                        candidates,
                        preferred_snippet=preferred_snippet,
                    )
                    # La cita es válida (existe literal en el chunk) pero pobre
                    # como evidencia: se intenta enriquecerla con otro fragmento
                    # literal del mismo ítem. Si no hay ninguno grounded, se
                    # conserva la corta -- verificada es verificada.
                    if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
                        richer = _rescue_paragraph_citation(item, candidates, category=category)
                        if richer and len(richer) > len(final_citation):
                            final_citation = richer
                    if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
                        final_citation = _widen_citation_with_chunk_context(final_citation, candidates)
                # Recorte al límite recién acá, sobre una cita ya verificada: el
                # techo es de legibilidad, no de validez. Y se recorta a la
                # ventana que contiene el dato del item, no al prefijo -- ver
                # `shorten_citation_to_evidence`.
                normalized_ref["citation"] = shorten_citation_to_evidence(final_citation, item)
                # ATR-02 (auditoría 2026-08-13): qué relación tiene lo que se
                # muestra con lo que el modelo realmente citó. Sin esto, tres
                # transformaciones distintas reescriben la cita después de
                # verificarla y nada aguas abajo puede distinguir el texto del
                # modelo del texto que puso el pipeline.
                normalized_ref["citation_llm"] = citation
                normalized_ref["citation_origin"] = (
                    "llm"
                    if _normalize_for_grounding(final_citation) == _normalize_for_grounding(citation)
                    else "ensanchada"
                )
                verified_refs.append(normalized_ref)
                continue

            if not _is_table_citation(citation):
                rescued_citation = _rescue_paragraph_citation(item, candidates, category=category)

            if rescued_citation:
                # FIX (auditoría 2026-08-13, hallazgo ATR-02): acá se hacía
                # `any_verified = True` y el item quedaba en `success`.
                #
                # Pero este camino se toma justamente cuando la cita QUE EL
                # MODELO DECLARÓ COMO EVIDENCIA no se pudo verificar contra
                # ningún chunk. El rescate busca si el `valor` o el
                # `texto_original` del item aparecen literalmente en algún chunk
                # y, si aparecen, los usa como cita. Que ese otro texto exista
                # en la página no prueba que respalde ESTE dato: puede ser el
                # mismo porcentaje de otra garantía, o la misma fecha de otro
                # plazo. La verificación anti-alucinación falló, y el sistema
                # la reemplazaba por otra que sí pasa.
                #
                # Se conserva el rescate -- tirar el item entero sería peor, y
                # el texto rescatado sí es literal del pliego -- pero deja de
                # contar como verificación: el item baja a `partial` y lleva una
                # marca explícita.
                rescued_refs_count += 1
                normalized_ref = dict(ref)
                normalized_ref["citation"] = rescued_citation
                normalized_ref["citation_llm"] = citation
                normalized_ref["citation_origin"] = "rescatada"
                # La cita rescatada también tiene su chunk de respaldo: es el
                # que hizo pasar `_verify_reference_grounded` dentro de
                # `_rescue_paragraph_citation`.
                _attach_chunk_identity(
                    normalized_ref, _find_grounding_chunk(rescued_citation, candidates)
                )
                verified_refs.append(normalized_ref)

        if verified_refs:
            item["source_references"] = verified_refs

        # Un item que sólo se sostiene con citas rescatadas no está verificado:
        # su evidencia declarada no existía en los chunks (ver arriba).
        if not any_verified and rescued_refs_count:
            rescued_items += 1
            if status == "success":
                item["extraction_status"] = "partial"
            item["_warning"] = "cita_reemplazada_por_rescate"

        if not any_verified and not rescued_refs_count:
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
            rescued_items=rescued_items,
        )

    return items


def _chunk_identity(chunk: dict[str, Any]) -> tuple[str, int]:
    return (str(chunk.get("document_id", "")), int(chunk.get("chunk_index", 0) or 0))


def _attach_chunk_identity(ref: dict[str, Any], chunk: dict[str, Any] | None) -> None:
    """Anota en la `source_reference` de qué chunk salió la evidencia (ATR-01).

    Además del `chunk_id`, se anota el `block_id` del bloque que efectivamente
    contiene la cita. Antes `block_id` sólo lo poblaba
    `_augment_identificacion_payload` -- y tomando `blocks[0]`, el PRIMER
    bloque del chunk, sin verificar cuál contenía la cita (hallazgo ATR-04).
    Para las otras siete categorías quedaba siempre vacío, porque el LLM no
    tiene forma de conocerlo: `_format_chunks` nunca expone identificadores de
    bloque.
    """
    if chunk is None:
        return

    chunk_id = chunk.get("id") or chunk.get("chunk_id")
    if chunk_id:
        ref["chunk_id"] = str(chunk_id)

    if ref.get("block_id"):
        return

    citation_normalized = _normalize_for_grounding(ref.get("citation", ""))
    if not citation_normalized:
        return

    source = chunk.get("source")
    blocks = source.get("blocks", []) if isinstance(source, dict) else (chunk.get("blocks") or [])
    if not isinstance(blocks, list):
        return

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_text = str(block.get("text") or block.get("content") or "")
        if not block_text:
            continue
        if citation_normalized in _normalize_for_grounding(block_text):
            block_id = block.get("block_id") or block.get("para_id")
            if block_id is not None:
                ref["block_id"] = str(block_id)
            return


def _retrieve_with_category_priority(
    *,
    query: str,
    analysis_id: str,
    top_k: int,
    keyword_query: str | None,
    category: str,
    correlation_id: str,
    category_boost: float = 0.20,  # Parametrizable para benchmark
) -> list[dict[str, Any]]:
    """Recupera chunks relevantes usando SCORING HÍBRIDO en vez de filtro rígido.

    CAMBIO ARQUITECTÓNICO v3 (2026-08-12):
    Ya NO filtra por categoría como criterio de exclusión. En su lugar:
    
    1. Busca en TODOS los chunks del analysis_id (sin filtro por categoría)
    2. Aplica category_boost al scoring de Azure:
       - Chunks con categoría target → boost +20%
       - Resto → score original de Azure
    3. Reordena y devuelve top_k
    
    Esto resuelve el problema fundamental: "información distribuida en chunks
    de distintas categorías no se pierde por clasificación imperfecta en chunking time".
    
    Por ejemplo:
        Chunk A: "La garantía será del 1%..." → primary_category="garantias"
        Chunk B: "Deberá presentarse junto con la oferta..." → primary_category="presentacion_ofertas"
    
    Query "garantias":
        ANTES: Solo recuperaba Chunk A (filtro rígido)
        AHORA: Recupera A y B, con A boosted (scoring híbrido)
    
    El LLM recibe contexto más amplio y decide cuál es evidencia relevante.
    """
    # PHASE 1: Búsqueda amplia - recuperar candidatos sin filtro rígido
    # Over-fetch para tener margen después de aplicar boost
    over_fetch_k = top_k * 3
    
    all_candidates = search_hybrid(
        query=query,
        analysis_id=analysis_id,
        top_k=over_fetch_k,
        keyword_query=keyword_query,
    )

    if not all_candidates:
        logger.warning(
            "retrieval_no_candidates",
            correlation_id=correlation_id,
            category=category,
            query=query[:120],
        )
        return []

    # PHASE 2: Category boost - señal, NO filtro
    # Boost configurable (default 20%) para chunks que tienen la categoría target
    CATEGORY_BOOST_FACTOR = 1.0 + category_boost  # e.g. 0.20 → 1.20
    
    scored_chunks: list[tuple[float, dict]] = []
    category_match_count = 0

    for rank, chunk in enumerate(all_candidates):
        # FIX (auditoría 2026-08-12, hallazgo M-2): usar el score real de
        # relevancia híbrida que Azure ya calculó (search_score, agregado en
        # shared/ports/azure_search.py) en vez de aproximarlo por posición
        # con 1.0/(rank+1). El rank sintético perdía la magnitud/distribución
        # real de relevancia entre candidatos -- dos chunks con scores de
        # Azure muy distintos (uno claramente más relevante que el resto)
        # terminaban con boosts comparables solo por estar en ranks
        # cercanos. `search_score` puede faltar en fuentes legacy/mocks de
        # test que no pasan por _search_azure; en ese caso se cae al rank
        # sintético anterior en vez de romper.
        base_score = chunk.get("search_score")
        if base_score is None:
            base_score = 1.0 / (rank + 1)

        # Category boost: verificar si el chunk tiene la categoría target
        has_category = (
            chunk.get("primary_category") == category
            or category in chunk.get("secondary_categories", [])
        )
        
        if has_category:
            boosted_score = base_score * CATEGORY_BOOST_FACTOR
            category_match_count += 1
        else:
            boosted_score = base_score
        
        scored_chunks.append((boosted_score, chunk))
    
    # PHASE 3: Reordenar por score combinado y devolver top_k
    # Como el score base ya viene de Azure en orden, solo necesitamos
    # reorganizar para que los boosted suban
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    final_chunks = [chunk for _score, chunk in scored_chunks[:top_k]]

    # Logging de distribución y recall
    category_distribution: dict[str, int] = {}
    for chunk in final_chunks:
        # FIX (auditoría 2026-08-13, hallazgo CHK-05): el default de `.get` no
        # alcanza -- la clave existe con valor None para los chunks que no se
        # pudieron clasificar, así que la distribución quedaba con una clave
        # None en vez de un nombre legible.
        primary = chunk.get("primary_category") or "sin_categoria"
        category_distribution[primary] = category_distribution.get(primary, 0) + 1

    target_chunks = sum(
        1
        for chunk in final_chunks
        if chunk.get("primary_category") == category
        or category in chunk.get("secondary_categories", [])
    )
    
    logger.info(
        "retrieval_hybrid_scoring",
        correlation_id=correlation_id,
        category=category,
        total_candidates=len(all_candidates),
        category_matches=category_match_count,
        final_chunks=len(final_chunks),
        target_chunks_in_final=target_chunks,
        category_distribution=category_distribution,
        strategy="hybrid_scoring_with_category_boost",
        category_boost_factor=f"{category_boost:.0%}",
    )
    
    return final_chunks


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
        
        # FIX MEDIUM (#14): Top-K configurable por categoría desde glossary.json
        from analysis.extraction.glossary import get_category_top_k
        category_top_k = get_category_top_k(result_key, default=settings.extraction_top_k)
        
        chunks = _retrieve_with_category_priority(
            query=query,
            analysis_id=analysis_id,
            top_k=category_top_k,
            keyword_query=keyword_query or None,
            category=result_key,
            correlation_id=correlation_id,
        )

        # CTX-02: primero el corte por relevancia, después el de presupuesto.
        # Al revés, el presupuesto se gastaría en la cola irrelevante.
        chunks = _drop_low_relevance_chunks(
            chunks,
            correlation_id=correlation_id,
            category=result_key,
        )

        chunks = _truncate_to_token_budget(
            chunks,
            settings.extraction_max_context_tokens,
            correlation_id=correlation_id,
            category=result_key,
        )

        # Logging de distribución de categorías recuperadas
        category_distribution: dict[str, int] = {}
        for chunk in chunks:
            # Ver el comentario equivalente en `_retrieve_with_category_priority`.
            primary = chunk.get("primary_category") or "sin_categoria"
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
            chunks_block=_format_chunks(chunks, state.get("document_labels")),
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
            normalized_object = _normalize_item(payload, fallback={"tipo": "estimacion_presupuesto"})
            if normalized_object.get("extraction_status") == "not_found" and _item_has_substantive_content(normalized_object):
                normalized_object["extraction_status"] = "partial"
            delta[state_field] = normalized_object
        else:
            if not isinstance(payload, list):
                logger.warning("payload_no_es_lista", category=result_key, tipo=type(payload).__name__)
                payload = []
            if result_key == "identificacion_procedimiento":
                payload = _augment_identificacion_payload(payload, chunks)
            normalized_items = [_normalize_item(item) for item in payload if isinstance(item, dict)]
            delta[state_field] = _normalize_mixed_not_found_items(normalized_items, category=result_key)

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
