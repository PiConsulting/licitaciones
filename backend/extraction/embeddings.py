from __future__ import annotations

from time import sleep
from uuid import UUID

import structlog

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
    if settings.is_development:
        from extraction.local.sentence_transformers_embeddings import LocalEmbeddingsAdapter

        return LocalEmbeddingsAdapter(model_name=settings.sentence_transformers_model)

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
    backoff_seconds = [1, 5, 15]
    batch_size = settings.azure_openai_embeddings_batch_size
    chunks_with_embeddings: list[dict] = []

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        texts = [chunk["content"] for chunk in batch]

        for attempt in range(1, retries + 1):
            try:
                embeddings = adapter.generate_embeddings(texts)
                for chunk, embedding in zip(batch, embeddings, strict=True):
                    chunk_copy = chunk.copy()
                    chunk_copy["embedding"] = embedding
                    chunks_with_embeddings.append(chunk_copy)
                break
            except Exception as exc:
                logger.warning(
                    "embedding_batch_failed",
                    correlation_id=str(correlation_id),
                    batch_start=batch_start,
                    attempt=attempt,
                    retries=retries,
                    error=sanitize_error_message(str(exc)),
                )
                if attempt >= retries:
                    raise TransientExtractionError(str(exc)) from exc
                sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    logger.info(
        "embedding_generation_completed",
        correlation_id=str(correlation_id),
        total_embeddings=len(chunks_with_embeddings),
    )
    return chunks_with_embeddings
