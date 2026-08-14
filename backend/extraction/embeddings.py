from __future__ import annotations

from time import sleep
from uuid import UUID

import structlog
from openai import APIError, APITimeoutError, RateLimitError

from extraction.errors import TransientExtractionError
from extraction.ports.embeddings_port import EmbeddingsPort
from shared.config import get_settings
from shared.security import sanitize_error_message

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


def embed_query(text: str) -> list[float]:
    """Vectoriza una consulta con el mismo modelo usado para indexar los chunks."""
    return _build_adapter().generate_embeddings([text])[0]


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
        return 16  # Default si no hay chunks
    
    # Estimar promedio de tokens usando primeros 100 chunks (o todos si hay menos)
    sample = chunks[:min(len(chunks), 100)]
    avg_tokens = sum(c.get("token_count", 700) for c in sample) / len(sample)
    
    # Calcular batch_size que no exceda max_tokens_per_batch
    dynamic_size = max(1, int(max_tokens_per_batch / avg_tokens))
    
    # No exceder el configured max
    settings = get_settings()
    return min(dynamic_size, settings.azure_openai_embeddings_batch_size)


def generate_embeddings(chunks: list[dict], correlation_id: str | UUID) -> list[dict]:
    settings = get_settings()
    adapter = _build_adapter()

    logger.info(
        "embedding_generation_started",
        correlation_id=str(correlation_id),
        total_chunks=len(chunks),
        mode="development" if settings.is_development else "production",
    )

    retries = settings.azure_openai_retry_attempts
    # FIX CRÍTICO (auditoría 2026-08-12, hallazgo C-1): esta variable se usaba en
    # los 4 bloques `except` de abajo sin estar nunca definida, así que cualquier
    # RateLimitError/APITimeoutError/APIError (eventos transitorios y rutinarios
    # contra Azure OpenAI, no excepcionales) crasheaba con NameError en el primer
    # intento en vez de reintentar -- tumbando el análisis completo del documento.
    backoff_seconds = [1, 5, 15]

    # Calcular batch_size dinámico basado en token_count de chunks
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
        
        # RAG ARCHITECTURE (2026-08-11): Embedding usa title + content para contexto,
        # pero el chunk almacenado mantiene content puro.
        #
        # ANTES: texts = [chunk["content"]]  → content ya incluía heading
        # AHORA: texts = [title + "\n\n" + content]  → contexto explícito para embedding
        texts = []
        for chunk in batch:
            title = chunk.get("title")
            content = chunk["content"]
            # Concatenar title si existe (para contexto semántico)
            embedding_input = f"{title}\n\n{content}" if title else content
            texts.append(embedding_input)

        for attempt in range(1, retries + 1):
            try:
                embeddings = adapter.generate_embeddings(texts)
                
                # Validar dimensiones de embeddings generados
                expected_dims = settings.azure_search_embedding_dimensions
                for i, embedding in enumerate(embeddings):
                    if len(embedding) != expected_dims:
                        raise RuntimeError(
                            f"Embedding dimension mismatch for chunk {batch_start + i}: "
                            f"got {len(embedding)}, expected {expected_dims}"
                        )
                
                # Añadir embeddings a chunks
                for chunk, embedding in zip(batch, embeddings, strict=True):
                    chunk_copy = chunk.copy()
                    chunk_copy["embedding"] = embedding
                    chunks_with_embeddings.append(chunk_copy)
                break
            # FIX LOW (#10): Separar Azure errors específicos para mejor handling
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
                    raise TransientExtractionError(f"Rate limit exceeded after {retries} attempts") from exc
                # Para rate limits, esperar más tiempo antes de reintentar
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
                    raise TransientExtractionError(f"API error after {retries} attempts: {exc}") from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
            except Exception as exc:
                # Errores inesperados (bugs de código, etc.) - loggear más detalles
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
                    raise TransientExtractionError(f"Unexpected error after {retries} attempts: {exc}") from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    logger.info(
        "embedding_generation_completed",
        correlation_id=str(correlation_id),
        total_embeddings=len(chunks_with_embeddings),
        batches_processed=len(range(0, len(chunks), batch_size)),
        avg_batch_size=len(chunks_with_embeddings) / max(len(range(0, len(chunks), batch_size)), 1),
    )
    return chunks_with_embeddings
