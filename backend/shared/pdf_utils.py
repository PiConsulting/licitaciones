from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def _open_document_from_bytes(content: bytes):
    try:
        import fitz

        return fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("No se pudo abrir el PDF") from exc


def get_pdf_metadata(content: bytes) -> tuple[int, bool]:
    """Return (page_count, is_password_protected)."""
    doc = _open_document_from_bytes(content)
    try:
        is_protected = bool(getattr(doc, "needs_pass", False) or getattr(doc, "is_encrypted", False))
        return doc.page_count, is_protected
    finally:
        doc.close()


def calculate_content_hash_from_pdf(content: bytes) -> str:
    """Calculate SHA-256 hash from PDF binary content."""
    return sha256(content).hexdigest()