from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from time import sleep
from uuid import UUID

import structlog
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient

from extraction.errors import TransientExtractionError
from extraction.ports.search_client_port import SearchClientPort
from shared.config import get_settings
from shared.security import sanitize_error_message

logger = structlog.get_logger(__name__)


class AzureSearchAdapter(SearchClientPort):
    def __init__(self, endpoint: str, key: str, index_name: str) -> None:
        self._endpoint = endpoint
        self._key = key
        self._index_name = index_name
        self._cached_index_fields: set[str] | None = None

    def _index_field_names(self) -> set[str]:
        if self._cached_index_fields is not None:
            return self._cached_index_fields

        client = SearchIndexClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._key),
        )
        index = client.get_index(self._index_name)
        self._cached_index_fields = {field.name for field in index.fields}
        return self._cached_index_fields

    def _to_index_document(self, document: dict) -> dict:
        allowed = self._index_field_names()
        return {key: value for key, value in document.items() if key in allowed}

    def upload_chunks(self, documents: list[dict]) -> None:
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._key),
        )
        result = client.upload_documents(documents=[self._to_index_document(document) for document in documents])
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
                    "section_path": str(doc.get("section_path", doc.get("section_key", "general"))),
                    "section_level": int(doc.get("section_level", 0) or 0),
                    "block_type": str(doc.get("block_type", "paragraph")),
                    "table_ref": json.dumps(doc.get("table_ref", None), ensure_ascii=True),
                }
            )

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=contents)


def _assert_index_contract(index, expected_dimensions: int) -> None:
    fields = {field.name: field for field in index.fields}
    required_fields = {"analysis_id", "section_key", "content", "document_id", "page_number", "chunk_index", "embedding"}
    missing_fields = sorted(name for name in required_fields if name not in fields)
    if missing_fields:
        raise RuntimeError("Índice de AI Search incompleto. Campos faltantes: " + ", ".join(missing_fields))

    for filter_field in ("analysis_id", "section_key"):
        if not bool(getattr(fields[filter_field], "filterable", False)):
            raise RuntimeError(f"Campo {filter_field} debe ser filterable en AI Search")

    vector_dimensions = getattr(fields["embedding"], "vector_search_dimensions", None)
    if int(vector_dimensions or 0) != expected_dimensions:
        raise RuntimeError(
            "Campo embedding incompatible. "
            f"Esperado dimensions={expected_dimensions}, recibido={vector_dimensions}"
        )


@lru_cache(maxsize=1)
def _validate_index_contract_cached(index_key: str) -> bool:
    settings = get_settings()
    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_key),
    )
    index = client.get_index(settings.azure_search_index_name)
    _assert_index_contract(index, expected_dimensions=settings.azure_search_embedding_dimensions)
    return True


def validate_index_contract() -> None:
    settings = get_settings()
    if settings.is_development:
        return

    index_key = f"{settings.azure_search_endpoint}:{settings.azure_search_index_name}:{settings.azure_search_embedding_dimensions}"
    _validate_index_contract_cached(index_key)


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
    if settings.is_production:
        validate_index_contract()
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
                "section_path": chunk.get("section_path", chunk.get("section_key", "general")),
                "section_level": int(chunk.get("section_level", 0) or 0),
                "block_type": chunk.get("block_type", "paragraph"),
                "table_ref": chunk.get("table_ref"),
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
                error=sanitize_error_message(str(exc)),
            )
            if attempt >= retries:
                raise TransientExtractionError(str(exc)) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
