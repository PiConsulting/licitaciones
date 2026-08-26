"""Adapter de Azure Document Intelligence detras del DocumentIntelligencePort. Unico archivo de esta carpeta que cambia si se reemplaza el proveedor de OCR/layout."""
from __future__ import annotations

from time import sleep
from uuid import UUID

import structlog
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)

from indexing.document_intelligence.markdown_parsing import _build_markdown_blocks
from indexing.errors import DocumentTextExtractionError, TransientExtractionError
from indexing.ports.document_intelligence_port import DocumentIntelligencePort
from infra.config import get_settings
from infra.security import sanitize_error_message, sanitize_url_for_logs

logger = structlog.get_logger(__name__)


class AzureDocumentIntelligenceAdapter(DocumentIntelligencePort):
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def extract_text(self, blob_url: str) -> list[dict]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import (
            AnalyzeDocumentRequest,
            DocumentContentFormat,
        )
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._api_key),
        )
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=AnalyzeDocumentRequest(url_source=blob_url),
            output_content_format=DocumentContentFormat.MARKDOWN,  # Markdown para estructura + result.paragraphs para bbox
        )
        result = poller.result(timeout=self._timeout_seconds)
        if not hasattr(result, "content"):
            raise DocumentTextExtractionError(
                "Azure DI result missing 'content' attribute - schema may have changed"
            )
        if result.content is None:
            raise DocumentTextExtractionError(
                "Azure DI returned None for content - document may be empty or corrupted"
            )

        blocks, telemetry = _build_markdown_blocks(result)
        if not blocks:
            raise DocumentTextExtractionError("No se detectó texto útil en el documento")

        logger.info("document_intelligence_markdown_blocks", **telemetry)
        return blocks


def _build_adapter() -> DocumentIntelligencePort:
    settings = get_settings()

    if (
        not settings.azure_document_intelligence_endpoint
        or not settings.azure_document_intelligence_key
    ):
        raise DocumentTextExtractionError("Falta configuración de Azure Document Intelligence")

    return AzureDocumentIntelligenceAdapter(
        endpoint=settings.azure_document_intelligence_endpoint,
        api_key=settings.azure_document_intelligence_key,
        timeout_seconds=settings.document_intelligence_timeout_seconds,
    )


def extract_text(
    blob_url: str,
    document_id: str | UUID,
    correlation_id: str | UUID,
    adapter: DocumentIntelligencePort | None = None,
) -> list[dict]:
    settings = get_settings()
    adapter = adapter or _build_adapter()

    logger.info(
        "text_extraction_started",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        blob_url=sanitize_url_for_logs(blob_url),
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
        except HttpResponseError as exc:
            is_last_attempt = attempt >= retries
            status_code = getattr(exc, "status_code", None)
            logger.warning(
                "text_extraction_http_error",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                attempt=attempt,
                retries=retries,
                status_code=status_code,
                error=sanitize_error_message(str(exc)),
            )
            if is_last_attempt:
                raise TransientExtractionError(f"HTTP error {status_code}: {exc}") from exc
            wait_time = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
            if status_code == 429:
                wait_time *= 2
            sleep(wait_time)
        except (ServiceRequestError, ServiceResponseError) as exc:
            is_last_attempt = attempt >= retries
            logger.warning(
                "text_extraction_service_error",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                attempt=attempt,
                retries=retries,
                error=sanitize_error_message(str(exc)),
                error_type=type(exc).__name__,
            )
            if is_last_attempt:
                raise TransientExtractionError(
                    f"Service error after {retries} attempts: {exc}"
                ) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
        except Exception as exc:
            is_last_attempt = attempt >= retries
            logger.error(
                "text_extraction_unexpected_error",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                attempt=attempt,
                retries=retries,
                error=sanitize_error_message(str(exc)),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            if is_last_attempt:
                raise TransientExtractionError(
                    f"Unexpected error after {retries} attempts: {exc}"
                ) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    raise TransientExtractionError("No se pudo extraer texto")
