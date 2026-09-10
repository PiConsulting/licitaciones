"""Llamada al LLM (Azure OpenAI), parseo de su respuesta, y manejo del presupuesto de tokens."""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any
import json
import re

from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

from infra.config import get_settings
from infra.adapters.azure_openai import get_azure_openai_client

logger = structlog.get_logger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_RELEVANCE_MIN_CHUNKS = 10
_RELEVANCE_MIN_RATIO = 0.4


@lru_cache(maxsize=1)
def _llm_concurrency_gate() -> threading.BoundedSemaphore | None:
    """Freno GLOBAL de llamadas al LLM en vuelo (Paso 1, plan
    rag-plan-latencia-2026-09-09). Vale para la suma de (temas en paralelo) x
    (documentos en paralelo del map-reduce) x (llamadas de síntesis): sin un
    tope acá, cuando esas capas se paralelicen la concurrencia real contra
    Azure se multiplica y dispara 429.

    `LLM_MAX_CONCURRENCY=0` (default) => sin límite => comportamiento idéntico
    al actual. Un valor > 0 activa el semáforo. `get_settings()` está
    cacheado, así que el límite es estable durante el proceso.
    """
    limit = int(get_settings().llm_max_concurrency or 0)
    if limit <= 0:
        return None
    logger.info("llm_concurrency_gate_enabled", limit=limit)
    return threading.BoundedSemaphore(limit)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(
    messages: list[tuple[str, str]], correlation_id: str
) -> tuple[dict[str, Any], dict[str, int]]:
    gate = _llm_concurrency_gate()
    if gate is not None:
        _wait_started = time.monotonic()
        gate.acquire()
        waited = time.monotonic() - _wait_started
        if waited > 1.0:
            logger.info(
                "llm_concurrency_gate_wait",
                correlation_id=correlation_id,
                waited_seconds=round(waited, 2),
            )
    try:
        return _call_llm_inner(messages, correlation_id)
    finally:
        # Se libera ANTES de que tenacity haga su backoff entre reintentos
        # (el sleep ocurre fuera de esta función), así el slot no queda
        # tomado durante la espera exponencial.
        if gate is not None:
            gate.release()


def _call_llm_inner(
    messages: list[tuple[str, str]], correlation_id: str
) -> tuple[dict[str, Any], dict[str, int]]:
    llm = get_azure_openai_client()

    try:
        bound = llm.bind(response_format={"type": "json_object"})
        response = bound.invoke(messages)
    except Exception:  # noqa: BLE001
        response = llm.invoke(messages)

    parsed = _parse_json_response(str(response.content))

    usage = (
        response.response_metadata.get("token_usage", {})
        if hasattr(response, "response_metadata")
        else {}
    )
    if not usage and hasattr(response, "response_metadata"):
        usage = response.response_metadata.get("usage", {}) or {}

    prompt_tokens = int(
        usage.get(
            "prompt_tokens",
            usage.get("input_tokens", usage.get("billed_units", {}).get("input_tokens", 0)),
        )
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
    # Azure OpenAI cachea automáticamente el prefijo estático de prompts >=1024
    # tokens (TTL ~5-10 min). Reporta el hit en prompt_tokens_details.cached_tokens.
    # Se loguea para verificar que el prefijo quedó byte-idéntico (los `{chunks}`
    # son lo único al final de cada prompt de extracción, plan 6.2).
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cached_tokens = int(
        (details.get("cached_tokens") if isinstance(details, dict) else 0)
        or usage.get("cache_read_input_tokens", 0)
        or 0
    )
    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
    }

    logger.info(
        "extractor_llm_invoked",
        correlation_id=correlation_id,
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
        total_tokens=token_usage["total_tokens"],
        cached_tokens=cached_tokens,
        cache_hit_rate=round(cached_tokens / prompt_tokens, 2) if prompt_tokens else 0.0,
    )
    return parsed, token_usage


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


@lru_cache(maxsize=1)
def _get_token_encoder() -> Any:
    """Encoder de tiktoken para medir el contexto con el tokenizer real del
    modelo. Si no está instalado, devuelve None y se cae a la aproximación por
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


def _truncate_to_token_budget(
    chunks: list[dict[str, Any]],
    budget: int,
    *,
    correlation_id: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Recorta la lista de chunks (ya ordenada por relevancia) para que quepa
    en `budget` tokens."""
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


def _drop_low_relevance_chunks(
    chunks: list[dict[str, Any]],
    *,
    correlation_id: str | None = None,
    category: str | None = None,
    min_chunks: int | None = None,
    min_ratio: float | None = None,
) -> list[dict[str, Any]]:
    """Saca la cola de chunks que el retrieval trajo por completar el `top_k`.
    Mantiene al menos `_RELEVANCE_MIN_CHUNKS` chunks y descarta los demás
    cuya relevancia (score) esté por debajo de `_RELEVANCE_MIN_RATIO` del mejor.
    """
    effective_min_chunks = max(1, int(min_chunks or _RELEVANCE_MIN_CHUNKS))
    effective_min_ratio = float(min_ratio if min_ratio is not None else _RELEVANCE_MIN_RATIO)

    if len(chunks) <= effective_min_chunks:
        return chunks

    def score_de(chunk: dict[str, Any]) -> float | None:
        # `retrieval_score` preserva la señal ajustada del retrieval
        # (boost/penalty y posible reranking). Si no está, cae al score
        # híbrido crudo por compatibilidad.
        valor = chunk.get("retrieval_score", chunk.get("search_score"))
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

    umbral = max(conocidos) * effective_min_ratio
    # El piso se cuenta por score, no por posición: la expansión
    # children→parent puede alterar el orden de la lista.
    protegidos = {
        indice
        for indice, _score in sorted(
            enumerate(scores),
            key=lambda par: (par[1] is None, -(par[1] or 0.0)),
        )[:effective_min_chunks]
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
            min_chunks=effective_min_chunks,
            min_ratio=round(effective_min_ratio, 5),
            score_max=round(max(conocidos), 5),
            score_umbral=round(umbral, 5),
            score_descartado_max=round(max(descartados), 5),
        )
    return conservados
