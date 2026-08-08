from __future__ import annotations

from pathlib import Path

from extraction.errors import DocumentTextExtractionError
from extraction.ports.document_intelligence_port import DocumentIntelligencePort
from shared.pdf_utils import extract_text_with_markitdown


class MarkItDownAdapter(DocumentIntelligencePort):
    def __init__(self, storage_root: str) -> None:
        self._root = Path(storage_root)

    def extract_text(self, blob_url: str) -> list[dict]:
        if not blob_url.startswith("local://"):
            raise DocumentTextExtractionError("URL local inválida")

        relative_path = blob_url.replace("local://", "", 1)
        file_path = self._root / relative_path
        if not file_path.exists():
            raise DocumentTextExtractionError(f"No existe el archivo local: {relative_path}")

        try:
            content = extract_text_with_markitdown(file_path)
        except Exception as exc:
            raise DocumentTextExtractionError(str(exc)) from exc

        # MarkItDown no conserva paginación exacta para todos los PDFs.
        return [{"page_number": 1, "content": content}]
