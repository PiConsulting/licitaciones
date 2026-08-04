from __future__ import annotations

from datetime import UTC, datetime

import structlog

from analysis.extraction.runner import extract_categories
from analysis.models import Analysis
from documents.models import Document
from extraction.ai_search import upload_chunks
from extraction.chunking import create_chunks
from extraction.document_intelligence import extract_text
from extraction.embeddings import generate_embeddings
from extraction.errors import DocumentTextExtractionError, ExtractionError
from shared.adapters.azure_blob_storage import AzureBlobStorageAdapter
from shared.adapters.local_blob_storage import LocalBlobStorageAdapter
from shared.config import get_settings
from shared.database import SessionLocal
from shared.ports.blob_storage import BlobStoragePort

logger = structlog.get_logger(__name__)


def _build_blob_storage() -> BlobStoragePort:
    settings = get_settings()
    if settings.is_production and settings.azure_blob_connection_string:
        return AzureBlobStorageAdapter(
            connection_string=settings.azure_blob_connection_string,
            container_name=settings.azure_blob_container_name,
        )
    return LocalBlobStorageAdapter(settings.local_blob_storage_path)


def extract_and_index(analysis_id: str) -> None:
    db = SessionLocal()
    blob_storage = _build_blob_storage()

    analysis = None
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
        if analysis is None:
            logger.error("analysis_not_found", analysis_id=analysis_id)
            return

        correlation_id = analysis.correlation_id
        documents = (
            db.query(Document)
            .filter(Document.analysis_id == analysis_id, Document.deleted_at.is_(None))
            .order_by(Document.uploaded_at.asc())
            .all()
        )

        total_docs = len(documents)
        if total_docs == 0:
            analysis.status = "error"
            analysis.current_stage = "No se pudo procesar el documento. Intentá nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
            return

        analysis.status = "extracting_text"
        analysis.current_stage = f"Extrayendo texto (1 de {total_docs} documentos)"
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        all_chunks: list[dict] = []
        for index, document in enumerate(documents, start=1):
            analysis.current_stage = f"Extrayendo texto ({index} de {total_docs} documentos)"
            analysis.updated_at = datetime.now(UTC)
            db.commit()

            blob_url = blob_storage.generate_download_url(document.blob_name)
            try:
                pages = extract_text(blob_url, document.id, correlation_id)
            except DocumentTextExtractionError:
                analysis.status = "error"
                analysis.current_stage = f"No se pudo leer el texto de «{document.filename}»"
                analysis.updated_at = datetime.now(UTC)
                db.commit()
                return

            chunks = create_chunks(pages, document.id, correlation_id)
            all_chunks.extend(chunks)

        analysis.status = "indexing"
        analysis.current_stage = "Indexando documentos"
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        chunks_with_embeddings = generate_embeddings(all_chunks, correlation_id)
        upload_chunks(chunks_with_embeddings, analysis_id, correlation_id)

        analysis.status = "analyzing"
        analysis.current_stage = "Analizando categorías (0/8 completadas)"
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        extract_categories(db, analysis)

        logger.info(
            "extract_and_index_completed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            documents=total_docs,
            chunks=len(all_chunks),
        )
    except ExtractionError as exc:
        logger.error(
            "extract_and_index_failed",
            analysis_id=analysis_id,
            correlation_id=analysis.correlation_id if analysis else None,
            error=str(exc),
            exc_info=True,
        )
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = "No se pudo procesar el documento. Intentá nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
    except Exception as exc:
        logger.error(
            "extract_and_index_unhandled_failed",
            analysis_id=analysis_id,
            correlation_id=analysis.correlation_id if analysis else None,
            error=str(exc),
            exc_info=True,
        )
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = "No se pudo procesar el documento. Intentá nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
