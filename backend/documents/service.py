from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from documents.models import Document
from shared.cosmos_container import get_cosmos_container
from shared.pdf_utils import calculate_content_hash_from_pdf


def calculate_content_hash(file_data: bytes) -> str:
    """Calculate SHA-256 hash from MarkItDown extracted text, with binary fallback."""
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


def get_document_by_id_cosmos(document_id: str) -> StoredDocument | None:
    container = get_cosmos_container()
    rows = list(
        container.query_items(
            query=(
                "SELECT TOP 1 c.document_id, c.filename, c.blob_name, c.created_by "
                "FROM c "
                "WHERE c.type = 'document' AND c.document_id = @document_id "
                "AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
            ),
            parameters=[{"name": "@document_id", "value": document_id}],
            enable_cross_partition_query=True,
        )
    )
    if not rows:
        return None

    row = rows[0]
    return StoredDocument(
        id=str(row.get("document_id", "")),
        filename=str(row.get("filename", "")),
        blob_name=str(row.get("blob_name", "")),
        created_by=str(row.get("created_by", "")),
    )
