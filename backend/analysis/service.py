import logging
import time
from dataclasses import dataclass
from datetime import date
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import String, and_, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from analysis.metadata_persistence import persist_analysis_metadata
from analysis.models import Analysis, AnalysisVersion, CurrentStage
from analysis.utils import calculate_confidence_avg
from documents.models import Document
from documents.schemas import DocumentResponse, DocumentWarning
from documents.service import calculate_content_hash
from extraction.ai_search import delete_analysis_chunks
from extraction.runner import extract_and_index
from shared.adapters.azure_blob_storage import AzureBlobStorageAdapter
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
) -> tuple[Analysis, list[Document], list[DocumentWarning], list[dict]]:
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

        persist_analysis_metadata(
            analysis=analysis,
            documents=documents,
            versions=[],
            event="analysis_created",
        )

        # Detectar duplicados acá, apenas se suben los archivos, en vez de
        # esperar a que el usuario le de a "iniciar análisis": el archivo ya
        # está en blob y hasheado en este punto, no hay motivo para
        # posponer el aviso.
        duplicates = find_duplicates_for_analysis(db, analysis.id, user_id)

        return analysis, documents, warnings, duplicates
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


def request_cancellation(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
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

    docs = db.query(Document).filter(Document.analysis_id == analysis.id).all()
    persist_analysis_metadata(
        analysis=analysis,
        documents=docs,
        versions=[],
        event="analysis_cancelled",
    )
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


def _extract_organism(extracted_data: dict | None) -> str | None:
    if not isinstance(extracted_data, dict):
        return None

    datos_procedimiento = extracted_data.get("datos_procedimiento")

    # Forma actual del pipeline: lista de GenericCategoryItem (`tipo`/`valor`).
    items = datos_procedimiento if isinstance(datos_procedimiento, list) else None
    if items is None and isinstance(datos_procedimiento, dict):
        # Forma legada, por si algún análisis viejo quedó persistido así.
        candidate = datos_procedimiento.get("items")
        items = candidate if isinstance(candidate, list) else None

    if items:
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("tipo") or item.get("field_name") or "").lower()
            if "organismo" not in label:
                continue
            value = item.get("valor") if "valor" in item else item.get("field_value")
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key, value in extracted_data.items():
        if "organismo" not in str(key).lower():
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def list_analyses(
    db: Session,
    *,
    user_id: str,
    search: str | None = None,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    primary_document = Document
    sort_columns = {
        "created_at": Analysis.created_at,
        "status": Analysis.status,
        "current_stage": Analysis.current_stage,
    }
    selected_sort = sort_columns.get(sort_by, Analysis.created_at)
    selected_order = asc if sort_order == "asc" else desc

    from users.models import User

    query = (
        db.query(
            Analysis,
            primary_document.filename.label("primary_document_name"),
            AnalysisVersion.extracted_data.label("extracted_data"),
            User.name.label("created_by_name"),
        )
        .outerjoin(
            primary_document,
            and_(
                primary_document.analysis_id == Analysis.id,
                primary_document.is_primary.is_(True),
                primary_document.deleted_at.is_(None),
            ),
        )
        .outerjoin(AnalysisVersion, AnalysisVersion.id == Analysis.current_version_id)
        .outerjoin(User, User.id == Analysis.created_by)
        .filter(
            Analysis.created_by == user_id,
            Analysis.deleted_at.is_(None),
        )
    )

    if status_filter:
        query = query.filter(Analysis.status == status_filter)

    if date_from:
        date_from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at >= date_from_dt)

    if date_to:
        date_to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at <= date_to_dt)

    if search and search.strip():
        normalized = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(func.coalesce(Analysis.analysis_name, "")).like(normalized),
                func.lower(func.coalesce(primary_document.filename, "")).like(normalized),
                func.lower(func.coalesce(cast(AnalysisVersion.extracted_data, String), "")).like(normalized),
                func.lower(func.coalesce(Analysis.id, "")).like(normalized),
            )
        )

    total = query.count()
    rows = (
        query.order_by(selected_order(selected_sort), desc(Analysis.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items: list[dict] = []
    for analysis, primary_document_name, extracted_data, created_by_name in rows:
        stage_progress = None
        if isinstance(analysis.extraction_metadata, dict):
            raw_progress = analysis.extraction_metadata.get("stage_progress")
            if isinstance(raw_progress, str):
                stage_progress = raw_progress

        items.append(
            {
                "id": analysis.id,
                "analysis_name": analysis.analysis_name,
                "status": analysis.status,
                "current_stage": analysis.current_stage,
                "stage_progress": stage_progress,
                "progress_percentage": analysis.progress_percentage or 0,
                "confidence_avg": calculate_confidence_avg(extracted_data),
                "created_at": analysis.created_at,
                "primary_document_name": primary_document_name,
                "organismo": _extract_organism(extracted_data),
                "created_by_name": created_by_name,
            }
        )

    return items, total


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
