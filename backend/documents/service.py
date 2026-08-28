from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from documents.models import Document
from infra.pdf_utils import calculate_content_hash_from_pdf


def calculate_content_hash(file_data: bytes) -> str:
    """Calculate SHA-256 hash from PDF binary content."""
    return calculate_content_hash_from_pdf(file_data)


@dataclass
class StoredDocument:
    id: str
    filename: str
    blob_name: str
    created_by: str


def get_document_by_id(db: Session, document_id: str) -> Document | None:
    stmt = select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()
