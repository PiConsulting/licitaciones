"""Llamada al LLM (Azure OpenAI), parseo de su respuesta, y manejo del presupuesto de tokens."""
from __future__ import annotations

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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(
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
) -> list[dict[str, Any]]:
    """Saca la cola de chunks que el retrieval trajo por completar el `top_k`.
    Mantiene al menos `_RELEVANCE_MIN_CHUNKS` chunks y descarta los demás
    cuya relevancia (score) esté por debajo de `_RELEVANCE_MIN_RATIO` del mejor.
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
