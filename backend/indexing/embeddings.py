from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from time import sleep
from uuid import UUID

import structlog
from openai import APIError, APITimeoutError, RateLimitError

from indexing.errors import TransientExtractionError
from indexing.ports.embeddings_port import EmbeddingsPort
from infra.config import get_settings
from infra.security import sanitize_error_message

logger = structlog.get_logger(__name__)


class AzureEmbeddingsAdapter(EmbeddingsPort):
    def __init__(self, endpoint: str, api_key: str, api_version: str, deployment: str) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._api_version = api_version
        self._deployment = deployment

    def generate_embeddings(self, inputs: list[str]) -> list[list[float]]:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
        )
        response = client.embeddings.create(input=inputs, model=self._deployment)
        return [list(item.embedding) for item in response.data]


def _build_adapter() -> EmbeddingsPort:
    settings = get_settings()

    missing: list[str] = []
    if not settings.azure_openai_endpoint.strip():
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not settings.azure_openai_api_key.strip():
        missing.append("AZURE_OPENAI_API_KEY")
    if not settings.azure_openai_api_version.strip():
        missing.append("AZURE_OPENAI_API_VERSION")
    if not settings.azure_openai_embedding_deployment.strip():
        missing.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    if missing:
        raise RuntimeError("Configuración de embeddings cloud incompleta: " + ", ".join(missing))

    return AzureEmbeddingsAdapter(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment=settings.azure_openai_embedding_deployment,
    )


def _build_query_id(analysis_id: str | None, category: str | None, normalized_query: str) -> str:
    """Construye query_id determinista para caché de embeddings.
    
    Args:
        analysis_id: ID del análisis (opcional para retrocompatibilidad)
        category: Categoría de extracción (opcional)
        normalized_query: Query ya normalizado (lowercase + whitespace único)
    
    Returns:
        Hash SHA256 del query normalizado (con analysis_id y category si disponibles)
    """
    if analysis_id and category:
        raw = f"{analysis_id}|{category}|{normalized_query}".encode("utf-8")
    else:
        # Retrocompatibilidad: cache solo por query si no hay contexto
        raw = normalized_query.encode("utf-8")
    
    return hashlib.sha256(raw).hexdigest()


def _normalize_query(query: str) -> str:
    """Normaliza query para caché determinista: lowercase + whitespace único."""
    return " ".join(query.strip().lower().split())


@lru_cache(maxsize=128)
def _embed_query_cached(query_id: str, normalized_text: str) -> tuple[float, ...]:
    """Vectoriza query con caché LRU. Key = (query_id, normalized_text) determinista.
    
    Args:
        query_id: Hash determinista (incluye analysis_id + category + query normalizado)
        normalized_text: Query normalizado (lowercase + whitespace único)
    
    Returns:
        Tuple de floats (embedding). Tuple en vez de list porque lru_cache requiere hashable.
    
    Note:
        Se cachean hasta 128 queries distintas. Eviction automática LRU.
        Cache es thread-safe por defecto (importante para FastAPI).
        Ambos parámetros son necesarios: query_id para el hash + normalized_text para embeddings.
        Como ambos son deterministas (normalizados), queries equivalentes comparten cache.
    """
    logger.debug(
        "embed_query_cache_miss",
        query_id=query_id[:16],
        query_preview=normalized_text[:60],
    )
    embedding = _build_adapter().generate_embeddings([normalized_text])[0]
    return tuple(embedding)


def embed_query(
    text: str,
    *,
    analysis_id: str | None = None,
    category: str | None = None,
) -> list[float]:
    """Vectoriza consulta con caché LRU para determinismo y reducción de costos.
    
    Args:
        text: Query de búsqueda
        analysis_id: ID del análisis (opcional, mejora cache key)
        category: Categoría de extracción (opcional, mejora cache key)
    
    Returns:
        Lista de floats (embedding de 3072 dimensiones)
    
    Note:
        - Queries idénticas retornan embeddings cacheados (sin llamar a Azure OpenAI)
        - Normalización: lowercase + whitespace único (queries "ABC" y "abc  " → mismo cache)
        - Cache key = hash(analysis_id + category + query normalizado)
        - Si analysis_id/category son None, cache solo por query text (retrocompatibilidad)
        - Cache size: 128 queries (eviction automática LRU)
    """
    normalized_text = _normalize_query(text)
    query_id = _build_query_id(analysis_id, category, normalized_text)
    embedding_tuple = _embed_query_cached(query_id, normalized_text)
    return list(embedding_tuple)


def _calculate_dynamic_batch_size(chunks: list[dict], max_tokens_per_batch: int = 20000) -> int:
    """Calcula batch_size dinámico basado en token_count real de chunks.

    Evita exceder límites de API cuando hay chunks muy largos (tablas extensas,
    párrafos densos). Usa promedio de los primeros 100 chunks como estimador.

    Args:
        chunks: Lista de chunks con campo 'token_count'
        max_tokens_per_batch: Máximo tokens por request a Azure OpenAI

    Returns:
        Batch size óptimo (mínimo 1, máximo configurado)
    """
    if not chunks:
        return 16
    sample = chunks[: min(len(chunks), 100)]
    avg_tokens = sum(c.get("token_count", 700) for c in sample) / len(sample)
    dynamic_size = max(1, int(max_tokens_per_batch / avg_tokens))
    settings = get_settings()
    return min(dynamic_size, settings.azure_openai_embeddings_batch_size)


# Niveles ancestros del heading (además de la hoja) antepuestos al contenido
# antes de embeber; los ancestros son hit-or-miss y a menudo boilerplate.
_EMBED_HEADING_ANCESTORS = 2
_EMBED_HEADING_MAX_CHARS = 220

# Heading levels puro ruido: PREFIX arranca con boilerplate administrativo, FULL es solo numeración/código sin título.
_HEADING_NOISE_PREFIX_RE = re.compile(
    r"^\s*(texto\s+aprobado\s+por|visto\s+el\s+expediente|disposici[oó]n\s+(di|n)|"
    r"resoluci[oó]n\s+(n|r)|expediente\s+(n|electr)|ex-\d)",
    re.IGNORECASE,
)
_HEADING_NOISE_FULL_RE = re.compile(
    r"^\s*(art[íi]culo\s+\d+\s*[°º.]?\s*|[\d.\-()°º/\s]+|[A-Z]{1,4}-[\d\-]+)\s*$",
    re.IGNORECASE,
)


def _is_noise_heading(level: str) -> bool:
    return bool(_HEADING_NOISE_PREFIX_RE.match(level) or _HEADING_NOISE_FULL_RE.match(level))


def _embedding_context(chunk: dict) -> str:
    """Encabezado que se antepone al contenido del chunk para embeber.

    FIX (2026-09-09, reindex A): antes se usaba solo `title` (= `heading_path[-1]`,
    la hoja). Los headings ancestros -- señal de "esto es un anexo / una
    garantía / un requisito" -- no llegaban al vector ni al BM25. Ahora se usa
    la hoja + hasta `_EMBED_HEADING_ANCESTORS` ancestros, saltando niveles que
    son boilerplate administrativo (`_HEADING_NOISE_RE`) y colapsando
    repeticiones consecutivas (los pliegos repiten el nombre del organismo).
    Sin `heading_path`, cae a `title` (comportamiento previo).
    """
    # Probado (reindex A) anteponer 2-3 niveles de heading_path: net +0.007 pero
    # con 4 regresiones -- descartado para el vector; el heading sigue llegando al BM25 vía content_tsv.
    title = chunk.get("title")
    return " ".join(str(title).split()).strip() if title else ""


def generate_embeddings(
    chunks: list[dict],
    correlation_id: str | UUID,
    adapter: EmbeddingsPort | None = None,
) -> list[dict]:
    settings = get_settings()
    adapter = adapter or _build_adapter()

    logger.info(
        "embedding_generation_started",
        correlation_id=str(correlation_id),
        total_chunks=len(chunks),
        mode="development" if settings.is_development else "production",
    )

    retries = settings.azure_openai_retry_attempts
    backoff_seconds = [1, 5, 15]
    batch_size = _calculate_dynamic_batch_size(chunks)
    logger.info(
        "embedding_batch_size_calculated",
        correlation_id=str(correlation_id),
        batch_size=batch_size,
        configured_max=settings.azure_openai_embeddings_batch_size,
    )

    chunks_with_embeddings: list[dict] = []

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        texts = []
        for chunk in batch:
            content = chunk["content"]
            context = _embedding_context(chunk)
            embedding_input = f"{context}\n\n{content}" if context else content
            texts.append(embedding_input)

        for attempt in range(1, retries + 1):
            try:
                embeddings = adapter.generate_embeddings(texts)
                expected_dims = settings.embedding_dimensions
                for i, embedding in enumerate(embeddings):
                    if len(embedding) != expected_dims:
                        raise RuntimeError(
                            f"Embedding dimension mismatch for chunk {batch_start + i}: "
                            f"got {len(embedding)}, expected {expected_dims}"
                        )
                for chunk, embedding in zip(batch, embeddings, strict=True):
                    chunk_copy = chunk.copy()
                    chunk_copy["embedding"] = embedding
                    # Se calcula acá (no en create_chunks) porque necesita el embedding, que ahí no existe todavía.
                    try:
                        from indexing.chunking.classification import (
                            classify_chunk_multilabel,
                        )

                        chunk_copy["category_scores"] = classify_chunk_multilabel(
                            chunk_copy, list(embedding)
                        )["category_scores"]
                    except Exception as exc:  # noqa: BLE001 - opcional, no debe tumbar el indexado
                        logger.warning(
                            "category_scores_computation_failed",
                            correlation_id=str(correlation_id),
                            chunk_index=chunk_copy.get("chunk_index"),
                            error=str(exc)[:200],
                        )
                    chunks_with_embeddings.append(chunk_copy)
                break
            except RateLimitError as exc:
                logger.warning(
                    "embedding_rate_limit",
                    correlation_id=str(correlation_id),
                    batch_start=batch_start,
                    attempt=attempt,
                    retries=retries,
                    error=sanitize_error_message(str(exc)),
                )
                if attempt >= retries:
                    raise TransientExtractionError(
                        f"Rate limit exceeded after {retries} attempts"
                    ) from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)] * 2)
            except APITimeoutError as exc:
                logger.warning(
                    "embedding_timeout",
                    correlation_id=str(correlation_id),
                    batch_start=batch_start,
                    attempt=attempt,
                    retries=retries,
                    error=sanitize_error_message(str(exc)),
                )
                if attempt >= retries:
                    raise TransientExtractionError(f"Timeout after {retries} attempts") from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
            except APIError as exc:
                logger.warning(
                    "embedding_api_error",
                    correlation_id=str(correlation_id),
                    batch_start=batch_start,
                    attempt=attempt,
                    retries=retries,
                    error=sanitize_error_message(str(exc)),
                    error_type=type(exc).__name__,
                )
                if attempt >= retries:
                    raise TransientExtractionError(
                        f"API error after {retries} attempts: {exc}"
                    ) from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
            except RuntimeError:
                # No es transitorio (mismatch de dimensiones/validación): reintentar no ayuda.
                raise
            except Exception as exc:
                logger.error(
                    "embedding_unexpected_error",
                    correlation_id=str(correlation_id),
                    batch_start=batch_start,
                    attempt=attempt,
                    retries=retries,
                    error=sanitize_error_message(str(exc)),
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                if attempt >= retries:
                    raise TransientExtractionError(
                        f"Unexpected error after {retries} attempts: {exc}"
                    ) from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    logger.info(
        "embedding_generation_completed",
        correlation_id=str(correlation_id),
        total_embeddings=len(chunks_with_embeddings),
        batches_processed=len(range(0, len(chunks), batch_size)),
        avg_batch_size=len(chunks_with_embeddings) / max(len(range(0, len(chunks), batch_size)), 1),
    )
    return chunks_with_embeddings
