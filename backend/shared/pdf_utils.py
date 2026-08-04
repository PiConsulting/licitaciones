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


def extract_text_with_markitdown(file_path: str | Path) -> str:
    try:
        from markitdown import MarkItDown
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "MarkItDown no está disponible. Instalá markitdown[pdf] para procesar archivos PDF."
        ) from exc

    converter = MarkItDown()
    result = converter.convert(str(file_path))
    content = (getattr(result, "text_content", "") or "").strip()
    if not content:
        raise ValueError("No se detectó texto útil en el documento")
    return content


def calculate_content_hash_from_pdf(content: bytes) -> str:
    """Hash normalized markdown/text extracted by MarkItDown, with binary fallback."""
    from tempfile import NamedTemporaryFile

    try:
        with NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(content)
            tmp.flush()
            extracted = extract_text_with_markitdown(tmp.name)
    except Exception:
        return sha256(content).hexdigest()

    normalized = " ".join(extracted.lower().split()).strip()
    if not normalized:
        return sha256(content).hexdigest()

    return sha256(normalized.encode("utf-8")).hexdigest()