"""Ciclo de vida de un analisis despues de creado: encolar extraccion, cancelar, eliminar (soft/hard)."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from analysis.models import Analysis, CurrentStage
from analysis.service.upload import _build_blob_storage
from documents.models import Document
from indexing.runner import extract_and_index
from infra.adapters.pgvector_search import delete_analysis_chunks
from infra.database import SessionLocal

logger = logging.getLogger(__name__)


def validate_analysis_ownership(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = (
        db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    )
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
        )

    if analysis.created_by != user_id:
        logger.warning(
            "Unauthorized access to analysis. user_id=%s analysis_id=%s owner_id=%s",
            user_id,
            analysis_id,
            analysis.created_by,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}
            },
        )

    return analysis


def enqueue_analysis(background_tasks: BackgroundTasks, analysis_id: str) -> None:
    """Enqueue sync extraction/indexing in FastAPI background threadpool."""
    background_tasks.add_task(extract_and_index, analysis_id)


def request_cancellation(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = (
        db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    )
    if analysis is None:
        raise ValueError("Analysis not found")

    if analysis.created_by != user_id:
        raise PermissionError("Only the owner can cancel this analysis")

    analysis.cancellation_requested = True
    if analysis.status not in {"analyzed", "error", "cancelled"}:
        analysis.status = "cancelled"
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.progress_percentage = max(analysis.progress_percentage or 0, 95)
        analysis.error_message = "El analisis fue cancelado por el usuario"
        analysis.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(analysis)
    return analysis


def delete_analysis(db: Session, analysis_id: str, user_id: str) -> str:
    analysis = validate_analysis_ownership(db, analysis_id, user_id)
    current_status = analysis.status.lower()

    if current_status in {"queued", "analyzing", "processing"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "ANALYSIS_DELETE_NOT_ALLOWED",
                    "message": "No podés eliminar un análisis en curso",
                }
            },
        )

    if current_status == "error":
        blob_storage = _build_blob_storage()
        documents = db.query(Document).filter(Document.analysis_id == analysis.id).all()
        for document in documents:
            blob_storage.delete(document.blob_name)
        delete_analysis_chunks(analysis.id)
        db.delete(analysis)
        db.commit()
        return "hard"

    now = datetime.now(UTC)
    analysis.deleted_at = now
    (
        db.query(Document)
        .filter(Document.analysis_id == analysis.id, Document.deleted_at.is_(None))
        .update({Document.deleted_at: now}, synchronize_session=False)
    )
    db.commit()
    return "soft"


def run_analysis_stub(analysis_id: str) -> None:
    """STUB sync processor for Story 2.3 background execution."""
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None:
            logger.error("[STUB] Analysis %s not found", analysis_id)
            return

        analysis.status = "analyzing"
        analysis.current_stage = "stub_processing"
        analysis.updated_at = datetime.now(UTC)
        db.commit()
        time.sleep(0.2)

        analysis.status = "completed"
        analysis.current_stage = None
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = None
            analysis.updated_at = datetime.now(UTC)
            db.commit()
        raise
    finally:
        db.close()
