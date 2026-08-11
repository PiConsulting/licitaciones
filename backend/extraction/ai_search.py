from __future__ import annotations

import json
from functools import lru_cache
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

    def delete_analysis_chunks(self, analysis_id: str) -> None:
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._key),
        )
        escaped_analysis_id = analysis_id.replace("'", "''")
        filter_expr = f"analysis_id eq '{escaped_analysis_id}'"

        while True:
            batch = [
                {"id": doc_id}
                for doc in client.search(search_text="*", top=500, select=["id"], filter=filter_expr)
                if (doc_id := doc.get("id"))
            ]
            if not batch:
                return
            client.delete_documents(documents=batch)
            # Rate limiting: 100ms entre batches previene exceder límites de Azure Search
            # con análisis muy grandes (50k+ chunks = 100+ batches)
            sleep(0.1)


def _assert_index_contract(index, expected_dimensions: int) -> None:
    fields = {field.name: field for field in index.fields}
    required_fields = {"analysis_id", "content", "document_id", "page_number", "chunk_index", "embedding"}
    missing_fields = sorted(name for name in required_fields if name not in fields)
    if missing_fields:
        raise RuntimeError("Índice de AI Search incompleto. Campos faltantes: " + ", ".join(missing_fields))

    if not bool(getattr(fields["analysis_id"], "filterable", False)):
        raise RuntimeError("Campo analysis_id debe ser filterable en AI Search")

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
    index_key = f"{settings.azure_search_endpoint}:{settings.azure_search_index_name}:{settings.azure_search_embedding_dimensions}"
    _validate_index_contract_cached(index_key)


def _build_adapter() -> SearchClientPort:
    settings = get_settings()
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
    )

    documents: list[dict] = []
    for chunk in chunks_with_embeddings:
        # Validar que chunk tiene embedding antes de construir documento
        if "embedding" not in chunk:
            raise ValueError(
                f"Chunk missing 'embedding' field: document_id={chunk.get('document_id')}, "
                f"chunk_index={chunk.get('chunk_index')}"
            )
        
        # Usar '::' como separador (menos ambiguo que '_' si document_id contiene underscores)
        chunk_id = f"{analysis_id}::{chunk['document_id']}::{chunk['chunk_index']}"
        table_ref = chunk.get("table_ref")
        documents.append(
            {
                "id": chunk_id,
                "analysis_id": str(analysis_id),
                "document_id": chunk["document_id"],
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "heading_path": list(chunk.get("heading_path") or []),
                "heading_level": int(chunk.get("heading_level", 0) or 0),
                "section_path": chunk.get("section_path", "general"),
                "block_type": chunk.get("block_type", "paragraph"),
                # Serializado una sola vez acá: tanto el índice de Azure Search
                # (Edm.String) como la metadata de Chroma requieren texto plano,
                # nunca un dict crudo.
                "table_ref": json.dumps(table_ref, ensure_ascii=True) if table_ref is not None else None,
                # `create_chunks` ya clasifica cada chunk, pero estos dos campos
                # no se subían al índice: quedaban en null para el 100% de los
                # chunks, el filtro por categoría del retrieval no matcheaba
                # nunca y toda extracción caía al fallback sin filtro.
                # `_to_index_document` descarta lo que el índice no declare, así
                # que incluirlos es seguro aunque el índice no esté migrado.
                "primary_category": chunk.get("primary_category"),
                "secondary_categories": list(chunk.get("secondary_categories") or []),
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


def delete_analysis_chunks(analysis_id: str | UUID) -> None:
    adapter = _build_adapter()
    adapter.delete_analysis_chunks(str(analysis_id))
