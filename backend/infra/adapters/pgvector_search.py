from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import structlog
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session, sessionmaker

from indexing.models import Chunk
from indexing.ports.search_client_port import SearchClientPort
from infra.database import _build_engine

logger = structlog.get_logger(__name__)


def _default_session_factory() -> Callable[[], Session]:
    engine = _build_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


class PgVectorSearchAdapter(SearchClientPort):
    """Implementa `SearchClientPort` contra la tabla `chunks` (pgvector),
    en reemplazo de `indexing.ai_search.AzureSearchAdapter`.
    """

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory or _default_session_factory()

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return
        with self._session_factory() as db:
            db.execute(insert(Chunk), documents)
            db.commit()

    def delete_analysis_chunks(self, analysis_id: str) -> int:
        with self._session_factory() as db:
            result = db.execute(delete(Chunk).where(Chunk.analysis_id == str(analysis_id)))
            db.commit()
            return result.rowcount or 0


def _build_adapter() -> SearchClientPort:
    return PgVectorSearchAdapter()


def upload_chunks(
    chunks_with_embeddings: list[dict],
    analysis_id: str | UUID,
    correlation_id: str | UUID,
    adapter: SearchClientPort | None = None,
) -> None:
    adapter = adapter or _build_adapter()

    logger.info(
        "pgvector_upload_started",
        correlation_id=str(correlation_id),
        analysis_id=str(analysis_id),
        total_chunks=len(chunks_with_embeddings),
    )

    removed = adapter.delete_analysis_chunks(str(analysis_id)) or 0
    if removed:
        logger.info(
            "pgvector_stale_chunks_removed",
            correlation_id=str(correlation_id),
            analysis_id=str(analysis_id),
            removed_chunks=removed,
            reason="re-indexación: se limpia el estado previo para no mezclar dos chunkings",
        )

    documents: list[dict] = []
    for chunk in chunks_with_embeddings:
        if "embedding" not in chunk:
            raise ValueError(
                f"Chunk missing 'embedding' field: document_id={chunk.get('document_id')}, "
                f"chunk_index={chunk.get('chunk_index')}"
            )

        chunk_id = f"{analysis_id}--{chunk['document_id']}--{chunk['chunk_index']}"

        parent_chunk_index = chunk.get("parent_chunk_index")
        parent_chunk_id = (
            f"{analysis_id}--{chunk['document_id']}--{parent_chunk_index}"
            if parent_chunk_index is not None
            else None
        )
        child_chunk_indices = chunk.get("child_chunk_indices") or []
        child_chunk_ids = [
            f"{analysis_id}--{chunk['document_id']}--{child_index}"
            for child_index in child_chunk_indices
        ]

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
                "title": chunk.get("title"),
                "block_type": chunk.get("block_type", "paragraph"),
                "table_ref": chunk.get("table_ref"),
                "source": chunk.get("source"),
                "primary_category": chunk.get("primary_category"),
                "secondary_categories": list(chunk.get("secondary_categories") or []),
                "blocks": chunk.get("blocks") or None,
                "content": chunk["content"],
                "embedding": chunk["embedding"],
                "chunk_type": chunk.get("chunk_type", "normal"),
                "parent_chunk_id": parent_chunk_id,
                "child_chunk_ids": child_chunk_ids,
            }
        )

    adapter.upload_chunks(documents)
    logger.info(
        "pgvector_upload_completed",
        correlation_id=str(correlation_id),
        analysis_id=str(analysis_id),
        uploaded_chunks=len(documents),
    )


def delete_analysis_chunks(analysis_id: str | UUID) -> int:
    adapter = _build_adapter()
    return adapter.delete_analysis_chunks(str(analysis_id)) or 0
