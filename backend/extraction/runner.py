from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from analysis.extraction.runner import extract_categories
from analysis.models import Analysis, CurrentStage
from analysis.progress import (
    build_stage_progress,
    calculate_timeout_minutes,
    mark_timeout_error,
    set_timeout_timestamps,
    update_stage_and_progress,
)
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
from shared.security import sanitize_error_message

logger = structlog.get_logger(__name__)

TOTAL_ANALYSIS_CATEGORIES = 8


def _now_for_comparison(target: datetime) -> datetime:
    now_utc = datetime.now(UTC)
    if target.tzinfo is None:
        return now_utc.replace(tzinfo=None)
    return now_utc


def _build_blob_storage() -> BlobStoragePort:
    settings = get_settings()
    if settings.is_production:
        missing: list[str] = []
        if not settings.azure_blob_connection_string.strip():
            missing.append("AZURE_BLOB_CONNECTION_STRING")
        if not settings.azure_blob_container_name.strip():
            missing.append("AZURE_BLOB_CONTAINER_NAME")
        if missing:
            raise RuntimeError("Configuración de Blob incompleta: " + ", ".join(missing))
        return AzureBlobStorageAdapter(
            connection_string=settings.azure_blob_connection_string,
            container_name=settings.azure_blob_container_name,
        )
    return LocalBlobStorageAdapter(settings.local_blob_storage_path)


def check_timeout_warning(db: Session, analysis_id: str, logger_instance) -> bool:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    if analysis is None or analysis.timeout_warning_at is None:
        return False

    now = _now_for_comparison(analysis.timeout_warning_at)
    if now >= analysis.timeout_warning_at and analysis.status == "processing":
        metadata = analysis.extraction_metadata or {}
        if not metadata.get("timeout_warning_reached"):
            metadata["timeout_warning_reached"] = True
            analysis.extraction_metadata = metadata
            analysis.updated_at = now
            db.commit()
        logger_instance.warning(
            "timeout_warning_threshold_reached",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis_id,
            timeout_at=analysis.timeout_at.isoformat() if analysis.timeout_at else None,
        )
        return True

    return False


def check_timeout_exceeded(db: Session, analysis_id: str, logger_instance) -> bool:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    if analysis is None or analysis.timeout_at is None:
        return False

    now = _now_for_comparison(analysis.timeout_at)
    if now < analysis.timeout_at:
        return False

    total_pages = (
        db.query(Document)
        .filter(Document.analysis_id == analysis_id, Document.deleted_at.is_(None))
        .with_entities(Document.page_count)
        .all()
    )
    timeout_minutes = calculate_timeout_minutes(sum(int(row[0] or 0) for row in total_pages))

    logger_instance.error(
        "analysis_timeout_exceeded",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis_id,
        timeout_at=analysis.timeout_at.isoformat(),
        timeout_minutes=timeout_minutes,
    )
    mark_timeout_error(analysis, timeout_minutes)
    analysis.updated_at = now
    db.commit()
    return True


def check_cancellation_requested(db: Session, analysis_id: str, logger_instance) -> bool:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    if analysis is None:
        return False

    if not analysis.cancellation_requested:
        return False

    logger_instance.info(
        "analysis_cancellation_requested",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis_id,
    )
    analysis.status = "cancelled"
    analysis.current_stage = CurrentStage.COMPLETED.value
    analysis.error_message = "El analisis fue cancelado por el usuario"
    analysis.progress_percentage = min(99, max(analysis.progress_percentage or 0, 35))
    analysis.updated_at = datetime.now(UTC)
    db.commit()
    return True


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
        total_pages = sum(int(document.page_count or 0) for document in documents)
        if total_docs == 0:
            analysis.status = "error"
            analysis.current_stage = CurrentStage.COMPLETED.value
            analysis.error_message = "No se pudo procesar el documento. Intenta nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
            return

        set_timeout_timestamps(analysis, total_pages)
        analysis.status = "processing"
        analysis.cancellation_requested = False
        analysis.error_message = None
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        update_stage_and_progress(
            db,
            analysis_id,
            CurrentStage.EXTRACTING_TEXT,
            stage_progress=build_stage_progress(CurrentStage.EXTRACTING_TEXT, done=1, total=total_docs),
            status="processing",
        )

        all_chunks: list[dict] = []
        for index, document in enumerate(documents, start=1):
            if check_cancellation_requested(db, analysis_id, logger):
                return
            if check_timeout_exceeded(db, analysis_id, logger):
                return
            check_timeout_warning(db, analysis_id, logger)

            update_stage_and_progress(
                db,
                analysis_id,
                CurrentStage.EXTRACTING_TEXT,
                progress_increment=min(10, int((index / total_docs) * 10)),
                stage_progress=build_stage_progress(CurrentStage.EXTRACTING_TEXT, done=index, total=total_docs),
                status="processing",
            )

            blob_url = blob_storage.generate_download_url(document.blob_name)
            try:
                pages = extract_text(blob_url, document.id, correlation_id)
            except DocumentTextExtractionError:
                analysis.status = "error"
                analysis.current_stage = CurrentStage.COMPLETED.value
                analysis.error_message = f"No se pudo leer el texto de {document.filename}"
                analysis.updated_at = datetime.now(UTC)
                db.commit()
                return

            chunks = create_chunks(pages, document.id, correlation_id)
            all_chunks.extend(chunks)

        if check_cancellation_requested(db, analysis_id, logger):
            return
        if check_timeout_exceeded(db, analysis_id, logger):
            return

        update_stage_and_progress(
            db,
            analysis_id,
            CurrentStage.INDEXING,
            progress_increment=10,
            stage_progress=build_stage_progress(CurrentStage.INDEXING),
            status="processing",
        )

        chunks_with_embeddings = generate_embeddings(all_chunks, correlation_id)
        upload_chunks(chunks_with_embeddings, analysis_id, correlation_id)

        update_stage_and_progress(
            db,
            analysis_id,
            CurrentStage.ANALYZING,
            stage_progress=build_stage_progress(CurrentStage.ANALYZING, done=0, total=TOTAL_ANALYSIS_CATEGORIES),
            status="processing",
        )

        if check_cancellation_requested(db, analysis_id, logger):
            return
        if check_timeout_exceeded(db, analysis_id, logger):
            return

        extract_categories(db, analysis)

        logger.info(
            "extract_and_index_completed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            documents=total_docs,
            chunks=len(all_chunks),
        )
    except ExtractionError as exc:
        logger.exception(
            "extract_and_index_failed",
            analysis_id=analysis_id,
            correlation_id=analysis.correlation_id if analysis else None,
            error=sanitize_error_message(str(exc)),
        )
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = CurrentStage.COMPLETED.value
            analysis.error_message = "No se pudo procesar el documento. Intenta nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
    except Exception as exc:
        logger.exception(
            "extract_and_index_unhandled_failed",
            analysis_id=analysis_id,
            correlation_id=analysis.correlation_id if analysis else None,
            error=sanitize_error_message(str(exc)),
        )
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = CurrentStage.COMPLETED.value
            analysis.error_message = "No se pudo procesar el documento. Intenta nuevamente"
            analysis.updated_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
