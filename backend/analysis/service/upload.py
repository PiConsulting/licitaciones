"""Alta de un analisis: validacion de PDFs, subida a blob storage y creacion de los registros de documento."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from analysis.models import Analysis
from analysis.service.duplicates import find_duplicates_for_analysis
from documents.models import Document
from documents.schemas import DocumentResponse, DocumentWarning
from documents.service import calculate_content_hash
from infra.adapters.azure_blob_storage import AzureBlobStorageAdapter
from infra.business_units import normalize_business_unit
from infra.config import get_settings
from infra.pdf_utils import get_pdf_metadata
from infra.ports.blob_storage import BlobStoragePort
from users.access import is_superadmin
from users.models import User

MAX_FILES = 10
MAX_PAGES = 300
WARNING_PAGES_THRESHOLD = 100


@dataclass
class IncomingUploadFile:
    filename: str
    content: bytes


def resolve_upload_business_unit(db: Session, user_id: str, requested: str | None) -> str:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        )

    if not is_superadmin(user):
        if not user.business_unit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "USER_WITHOUT_BUSINESS_UNIT",
                        "message": "Tu usuario no tiene unidad de negocio asignada",
                    }
                },
            )
        return user.business_unit

    if requested is None or not requested.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "BUSINESS_UNIT_REQUIRED",
                    "message": "Seleccioná la unidad de negocio",
                }
            },
        )

    resolved = normalize_business_unit(requested)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "BUSINESS_UNIT_INVALID",
                    "message": "La unidad de negocio no es válida",
                }
            },
        )
    return resolved


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
    analysis_name: str | None = None,
    business_unit: str | None = None,
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
            detail={
                "error": {
                    "code": "MISSING_PRIMARY",
                    "message": "Seleccioná cuál es el pliego principal",
                }
            },
        )

    resolved_business_unit = resolve_upload_business_unit(db, user_id, business_unit)
    blob_storage = _build_blob_storage()
    uploaded_blob_names: list[str] = []

    try:
        analysis = Analysis(
            created_by=user_id,
            status="draft",
            analysis_name=analysis_name,
            business_unit=resolved_business_unit,
        )
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
