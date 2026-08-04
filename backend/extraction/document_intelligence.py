from __future__ import annotations

from pathlib import Path
from time import sleep
from uuid import UUID

import structlog

from extraction.errors import DocumentTextExtractionError, TransientExtractionError
from extraction.ports.document_intelligence_port import DocumentIntelligencePort
from shared.pdf_utils import extract_text_with_markitdown
from shared.config import get_settings

logger = structlog.get_logger(__name__)


class AzureDocumentIntelligenceAdapter(DocumentIntelligencePort):
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def extract_text(self, blob_url: str) -> list[dict]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._api_key),
        )
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request={"url_source": blob_url},
        )
        result = poller.result(timeout=self._timeout_seconds)

        pages: list[dict] = []
        for page in result.pages:
            lines = [line.content for line in page.lines] if page.lines else []
            content = "\n".join(lines).strip()
            if content:
                pages.append({"page_number": int(page.page_number), "content": content})

        if not pages:
            raise DocumentTextExtractionError("No se detectó texto útil en el documento")
        return pages


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


def _build_adapter() -> DocumentIntelligencePort:
    settings = get_settings()
    if settings.is_development:
        return MarkItDownAdapter(settings.local_blob_storage_path)

    if not settings.azure_document_intelligence_endpoint or not settings.azure_document_intelligence_key:
        raise DocumentTextExtractionError("Falta configuración de Azure Document Intelligence")

    return AzureDocumentIntelligenceAdapter(
        endpoint=settings.azure_document_intelligence_endpoint,
        api_key=settings.azure_document_intelligence_key,
        timeout_seconds=settings.document_intelligence_timeout_seconds,
    )


def extract_text(blob_url: str, document_id: str | UUID, correlation_id: str | UUID) -> list[dict]:
    settings = get_settings()
    adapter = _build_adapter()

    logger.info(
        "text_extraction_started",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        blob_url=blob_url,
        mode="development" if settings.is_development else "production",
    )

    retries = settings.document_intelligence_retry_attempts
    backoff_seconds = [1, 5, 15]

    for attempt in range(1, retries + 1):
        try:
            pages = adapter.extract_text(blob_url)
            logger.info(
                "text_extraction_completed",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                pages_extracted=len(pages),
                attempt=attempt,
            )
            return pages
        except DocumentTextExtractionError:
            raise
        except Exception as exc:
            is_last_attempt = attempt >= retries
            logger.warning(
                "text_extraction_attempt_failed",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                attempt=attempt,
                retries=retries,
                error=str(exc),
            )
            if is_last_attempt:
                raise TransientExtractionError(str(exc)) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    raise TransientExtractionError("No se pudo extraer texto")
