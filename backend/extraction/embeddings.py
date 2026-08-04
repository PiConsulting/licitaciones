from __future__ import annotations

import hashlib
from time import sleep
from uuid import UUID

import structlog

from extraction.errors import TransientExtractionError
from extraction.ports.embeddings_port import EmbeddingsPort
from shared.config import get_settings

logger = structlog.get_logger(__name__)

_VECTOR_SIZE = 1536


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


class LocalEmbeddingsAdapter(EmbeddingsPort):
    def generate_embeddings(self, inputs: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in inputs:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [0.0] * _VECTOR_SIZE
            for index in range(_VECTOR_SIZE):
                vector[index] = digest[index % len(digest)] / 255.0
            vectors.append(vector)
        return vectors


def _build_adapter() -> EmbeddingsPort:
    settings = get_settings()
    if settings.use_local_adapters:
        return LocalEmbeddingsAdapter()

    return AzureEmbeddingsAdapter(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment=settings.azure_openai_embedding_deployment,
    )


def generate_embeddings(chunks: list[dict], correlation_id: str | UUID) -> list[dict]:
    settings = get_settings()
    adapter = _build_adapter()

    logger.info(
        "embedding_generation_started",
        correlation_id=str(correlation_id),
        total_chunks=len(chunks),
        mode="local" if settings.use_local_adapters else "cloud",
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
                    error=str(exc),
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
