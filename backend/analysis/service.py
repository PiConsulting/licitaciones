from dataclasses import dataclass
from datetime import UTC, datetime
from fastapi import BackgroundTasks
from hashlib import sha256
import logging
from pathlib import Path
import time
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from analysis.models import Analysis
from documents.models import Document
from documents.service import calculate_content_hash
from documents.schemas import DocumentResponse, DocumentWarning
from extraction.runner import extract_and_index
from shared.adapters.azure_blob_storage import AzureBlobStorageAdapter
from shared.adapters.local_blob_storage import LocalBlobStorageAdapter
from shared.config import get_settings
from shared.database import SessionLocal
from shared.pdf_utils import get_pdf_metadata
from shared.ports.blob_storage import BlobStoragePort
from users.models import User

MAX_FILES = 10
MAX_PAGES = 300
WARNING_PAGES_THRESHOLD = 100

logger = logging.getLogger(__name__)


@dataclass
class IncomingUploadFile:
    filename: str
    content: bytes


def _sanitize_filename(filename: str) -> str:
    sanitized = Path(filename).name
    return sanitized[:255]


def _build_blob_storage() -> BlobStoragePort:
    settings = get_settings()
    if settings.is_production and settings.azure_blob_connection_string:
        return AzureBlobStorageAdapter(
            connection_string=settings.azure_blob_connection_string,
            container_name=settings.azure_blob_container_name,
        )
    return LocalBlobStorageAdapter(settings.local_blob_storage_path)


def _validate_pdf_or_raise(filename: str, content: bytes) -> tuple[int, DocumentWarning | None]:
    try:
        page_count, is_encrypted = get_pdf_metadata(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PDF_CORRUPTED",
                    "message": f"No se pudo abrir «{filename}»: el archivo está dañado. Volvé a descargarlo del portal del organismo y subilo de nuevo",
                }
            },
        ) from exc

    if is_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PDF_PASSWORD_PROTECTED",
                    "message": f"«{filename}» está protegido con contraseña. Quitale la protección y volvé a subirlo",
                }
            },
        )

    if page_count > MAX_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PDF_TOO_MANY_PAGES",
                    "message": f"«{filename}» tiene {page_count} páginas y el máximo es 300",
                }
            },
        )

    warning = None
    if page_count > WARNING_PAGES_THRESHOLD:
        warning_minutes = max(1, page_count // 10)
        warning = DocumentWarning(
            filename=filename,
            message=f"«{filename}» tiene {page_count} páginas. El análisis puede demorar hasta {warning_minutes} minutos",
        )

    return page_count, warning


def create_analysis_with_documents(
    db: Session,
    user_id: str,
    files: list[IncomingUploadFile],
    primary_file_index: int,
) -> tuple[Analysis, list[Document], list[DocumentWarning]]:
    if len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "NO_FILES", "message": "Debés subir al menos un archivo"}},
        )

    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "TOO_MANY_FILES",
                    "message": f"Podés subir hasta 10 archivos por análisis y seleccionaste {len(files)}",
                }
            },
        )

    if len(files) == 1:
        primary_file_index = 0

    if primary_file_index < 0 or primary_file_index >= len(files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "MISSING_PRIMARY", "message": "Seleccioná cuál es el pliego principal"}},
        )

    blob_storage = _build_blob_storage()
    uploaded_blob_names: list[str] = []

    try:
        analysis = Analysis(created_by=user_id, status="draft")
        db.add(analysis)
        db.flush()

        warnings: list[DocumentWarning] = []
        documents: list[Document] = []

        for index, incoming_file in enumerate(files):
            safe_name = _sanitize_filename(incoming_file.filename)
            page_count, warning = _validate_pdf_or_raise(safe_name, incoming_file.content)
            if warning:
                warnings.append(warning)

            blob_name = f"{analysis.id}/{uuid4()}-{safe_name}"
            blob_storage.upload(blob_name, incoming_file.content)
            uploaded_blob_names.append(blob_name)

            document = Document(
                analysis_id=analysis.id,
                filename=safe_name,
                blob_name=blob_name,
                file_size_bytes=len(incoming_file.content),
                page_count=page_count,
                is_primary=index == primary_file_index,
                sha256_hash=sha256(incoming_file.content).hexdigest(),
                content_hash=calculate_content_hash(incoming_file.content),
                created_by=user_id,
            )
            db.add(document)
            documents.append(document)

        db.commit()
        db.refresh(analysis)
        for document in documents:
            db.refresh(document)

        return analysis, documents, warnings
    except Exception:
        db.rollback()
        for blob_name in uploaded_blob_names:
            blob_storage.delete(blob_name)
        raise


def to_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        page_count=document.page_count,
        file_size_bytes=document.file_size_bytes,
        is_primary=document.is_primary,
    )


def validate_analysis_ownership(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
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
            detail={"error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}},
        )

    return analysis


def check_duplicates(
    db: Session,
    content_hash: str,
    *,
    exclude_analysis_id: str | None = None,
    user_id: str | None = None,
) -> dict | None:
    stmt = (
        select(
            Document.id.label("document_id"),
            Document.filename,
            Document.content_hash,
            Analysis.id.label("analysis_id"),
            Analysis.created_at,
            Analysis.status,
            User.email.label("created_by_email"),
            User.name.label("created_by_name"),
        )
        .join(Analysis, Document.analysis_id == Analysis.id)
        .join(User, Analysis.created_by == User.id)
        .where(
            and_(
                Document.content_hash == content_hash,
                Analysis.deleted_at.is_(None),
                Document.deleted_at.is_(None),
                Analysis.status.in_(["completed", "analyzing", "analyzed"]),
            )
        )
    )

    if exclude_analysis_id:
        stmt = stmt.where(Analysis.id != exclude_analysis_id)

    if user_id:
        stmt = stmt.where(Analysis.created_by == user_id)

    result = db.execute(stmt.order_by(Analysis.created_at.desc()).limit(1)).first()
    if result is None:
        return None

    return {
        "document_id": str(result.document_id),
        "filename": result.filename,
        "analysis_id": str(result.analysis_id),
        "created_at": result.created_at.isoformat(),
        "status": result.status,
        "created_by_email": result.created_by_email,
        "created_by_name": result.created_by_name,
    }


def find_duplicates_for_analysis(db: Session, analysis_id: str, user_id: str) -> list[dict]:
    documents = (
        db.query(Document)
        .filter(
            Document.analysis_id == analysis_id,
            Document.deleted_at.is_(None),
            Document.content_hash.is_not(None),
        )
        .all()
    )

    duplicates: list[dict] = []
    for document in documents:
        duplicate = check_duplicates(
            db,
            document.content_hash or "",
            exclude_analysis_id=analysis_id,
            user_id=user_id,
        )
        if duplicate is None:
            continue

        duplicates.append(
            {
                "document_id": document.id,
                "filename": document.filename,
                "existing_analysis_id": duplicate["analysis_id"],
                "created_at": duplicate["created_at"],
                "created_by": duplicate["created_by_name"] or duplicate["created_by_email"],
                "status": duplicate["status"],
            }
        )

    return duplicates


def enqueue_analysis(background_tasks: BackgroundTasks, analysis_id: str) -> None:
    """Enqueue sync extraction/indexing in FastAPI background threadpool."""
    background_tasks.add_task(extract_and_index, analysis_id)


def run_analysis_stub(analysis_id: str) -> None:
    """STUB sync processor for Story 2.3 background execution."""
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
        if analysis is None:
            logger.error("[STUB] Analysis %s not found", analysis_id)
            return

        analysis.status = "analyzing"
        analysis.current_stage = "stub_processing"
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        # Keep the delay short to avoid slowing down test suite significantly.
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
