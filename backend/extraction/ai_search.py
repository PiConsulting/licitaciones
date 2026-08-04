from __future__ import annotations

import json
from pathlib import Path
from time import sleep
from uuid import UUID

import structlog

from extraction.errors import TransientExtractionError
from extraction.ports.search_client_port import SearchClientPort
from shared.config import get_settings

logger = structlog.get_logger(__name__)


class AzureSearchAdapter(SearchClientPort):
    def __init__(self, endpoint: str, key: str, index_name: str) -> None:
        self._endpoint = endpoint
        self._key = key
        self._index_name = index_name

    def upload_chunks(self, documents: list[dict]) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._key),
        )
        result = client.upload_documents(documents=documents)
        failed = [item for item in result if not item.succeeded]
        if failed:
            raise TransientExtractionError(f"Fallaron {len(failed)} documentos en upload")


class LocalJsonSearchAdapter(SearchClientPort):
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir) / "analysis_index"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return

        analysis_id = documents[0]["analysis_id"]
        target = self._base_dir / f"{analysis_id}.jsonl"
        with target.open("w", encoding="utf-8") as handle:
            for doc in documents:
                handle.write(json.dumps(doc, ensure_ascii=True) + "\n")


class LocalChromaSearchAdapter(SearchClientPort):
    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return

        import chromadb

        client = chromadb.PersistentClient(path=str(self._persist_dir))
        collection = client.get_or_create_collection(name="analysis_chunks")

        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []
        contents: list[str] = []

        for doc in documents:
            ids.append(doc["id"])
            embeddings.append(list(doc["embedding"]))
            contents.append(doc["content"])
            metadatas.append(
                {
                    "analysis_id": str(doc["analysis_id"]),
                    "document_id": str(doc["document_id"]),
                    "page_number": int(doc["page_number"]),
                    "chunk_index": int(doc["chunk_index"]),
                    "section_key": str(doc.get("section_key", "general")),
                }
            )

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=contents)


def _build_adapter() -> SearchClientPort:
    settings = get_settings()
    if settings.is_development:
        return LocalChromaSearchAdapter(settings.chroma_persist_directory)
    return AzureSearchAdapter(
        endpoint=settings.azure_search_endpoint,
        key=settings.azure_search_key,
        index_name=settings.azure_search_index_name,
    )


def upload_chunks(chunks_with_embeddings: list[dict], analysis_id: str | UUID, correlation_id: str | UUID) -> None:
    settings = get_settings()
    adapter = _build_adapter()

    logger.info(
        "search_upload_started",
        correlation_id=str(correlation_id),
        analysis_id=str(analysis_id),
        total_chunks=len(chunks_with_embeddings),
        mode="development" if settings.is_development else "production",
    )

    documents: list[dict] = []
    for chunk in chunks_with_embeddings:
        chunk_id = f"{analysis_id}_{chunk['document_id']}_{chunk['chunk_index']}"
        documents.append(
            {
                "id": chunk_id,
                "analysis_id": str(analysis_id),
                "document_id": chunk["document_id"],
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "section_key": chunk.get("section_key", "general"),
                "content": chunk["content"],
                "embedding": chunk["embedding"],
            }
        )

    retries = settings.azure_search_retry_attempts
    backoff_seconds = [2, 10, 30]

    for attempt in range(1, retries + 1):
        try:
            batch_size = settings.azure_search_upload_batch_size
            for start in range(0, len(documents), batch_size):
                adapter.upload_chunks(documents[start : start + batch_size])
            logger.info(
                "search_upload_completed",
                correlation_id=str(correlation_id),
                analysis_id=str(analysis_id),
                uploaded_chunks=len(documents),
            )
            return
        except Exception as exc:
            logger.warning(
                "search_upload_attempt_failed",
                correlation_id=str(correlation_id),
                analysis_id=str(analysis_id),
                attempt=attempt,
                retries=retries,
                error=str(exc),
            )
            if attempt >= retries:
                raise TransientExtractionError(str(exc)) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
