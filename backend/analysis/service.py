from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pypdf
from fastapi import HTTPException, status
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from analysis.models import Analysis
from documents.models import Document
from documents.schemas import DocumentResponse, DocumentWarning
from shared.adapters.azure_blob_storage import AzureBlobStorageAdapter
from shared.adapters.local_blob_storage import LocalBlobStorageAdapter
from shared.config import get_settings
from shared.ports.blob_storage import BlobStoragePort

MAX_FILES = 10
MAX_PAGES = 300
WARNING_PAGES_THRESHOLD = 100


@dataclass
class IncomingUploadFile:
    filename: str
    content: bytes


def _sanitize_filename(filename: str) -> str:
    sanitized = Path(filename).name
    return sanitized[:255]


def _build_blob_storage() -> BlobStoragePort:
    settings = get_settings()
    if not settings.use_local_adapters and settings.azure_blob_connection_string:
        return AzureBlobStorageAdapter(
            connection_string=settings.azure_blob_connection_string,
            container_name=settings.azure_blob_container_name,
        )
    return LocalBlobStorageAdapter(settings.local_blob_storage_path)


def _validate_pdf_or_raise(filename: str, content: bytes) -> tuple[int, DocumentWarning | None]:
    try:
        reader = pypdf.PdfReader(BytesIO(content))
    except PdfReadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PDF_CORRUPTED",
                    "message": f"No se pudo abrir «{filename}»: el archivo está dañado. Volvé a descargarlo del portal del organismo y subilo de nuevo",
                }
            },
        ) from exc
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

    if reader.is_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PDF_PASSWORD_PROTECTED",
                    "message": f"«{filename}» está protegido con contraseña. Quitale la protección y volvé a subirlo",
                }
            },
        )

    page_count = len(reader.pages)
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
        analysis = Analysis(created_by=user_id, status="queued")
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
