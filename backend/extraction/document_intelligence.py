from __future__ import annotations

from pathlib import Path
from time import sleep
from uuid import UUID

import structlog
from structlog.typing import EventDict

from extraction.errors import DocumentTextExtractionError, TransientExtractionError
from extraction.ports.document_intelligence_port import DocumentIntelligencePort
from shared.config import get_settings
from shared.pdf_utils import extract_text_with_markitdown
from shared.security import sanitize_error_message, sanitize_url_for_logs

logger = structlog.get_logger(__name__)

_EXCLUDED_PARAGRAPH_ROLES = {"pageHeader", "pageFooter", "footnote"}
_HEADING_ROLES = {"title", "sectionHeading"}


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _first_page_number(item: object) -> int:
    regions = getattr(item, "bounding_regions", None) or []
    for region in regions:
        page_number = getattr(region, "page_number", None)
        if page_number is not None:
            return _safe_int(page_number, default=1)
    return 1


def _first_span_offset(item: object, fallback: int) -> int:
    spans = getattr(item, "spans", None) or []
    if spans:
        first_offset = getattr(spans[0], "offset", None)
        if first_offset is not None:
            return _safe_int(first_offset, default=fallback)
    return fallback


def _normalize_cell_kind(kind: object) -> str:
    if kind is None:
        return ""
    return str(kind).strip()


def _serialize_table_rows(table: object, table_id: str) -> list[dict]:
    row_count = _safe_int(getattr(table, "row_count", 0), default=0)
    column_count = _safe_int(getattr(table, "column_count", 0), default=0)
    cells = list(getattr(table, "cells", None) or [])

    if row_count <= 0:
        row_count = max((_safe_int(getattr(cell, "row_index", 0), default=0) for cell in cells), default=-1) + 1
    if column_count <= 0:
        column_count = max((_safe_int(getattr(cell, "column_index", 0), default=0) for cell in cells), default=-1) + 1

    if row_count <= 0 or column_count <= 0:
        return []

    matrix = [["" for _ in range(column_count)] for _ in range(row_count)]
    header_by_col: dict[int, str] = {}
    header_rows: set[int] = set()

    for cell in cells:
        row_index = _safe_int(getattr(cell, "row_index", 0), default=0)
        col_index = _safe_int(getattr(cell, "column_index", 0), default=0)
        if row_index < 0 or col_index < 0:
            continue
        if row_index >= row_count or col_index >= column_count:
            continue

        content = str(getattr(cell, "content", "") or "").strip()
        kind = _normalize_cell_kind(getattr(cell, "kind", ""))
        if content:
            matrix[row_index][col_index] = content

        kind_lower = kind.lower()
        if kind_lower in {"columnheader", "stubhead"} and content:
            header_by_col[col_index] = content
            header_rows.add(row_index)

    for col_index in range(column_count):
        if not header_by_col.get(col_index):
            header_by_col[col_index] = f"col_{col_index + 1}"

    row_blocks: list[dict] = []
    table_page = _first_page_number(table)
    table_order = _first_span_offset(table, fallback=0)

    for row_index, row in enumerate(matrix):
        if row_index in header_rows:
            continue
        if not any(cell.strip() for cell in row):
            continue

        fragments = [f"Tabla {table_id}", f"Fila {row_index + 1}"]
        citation_headers: list[str] = []
        for col_index, cell_value in enumerate(row):
            normalized = cell_value.strip()
            if not normalized:
                continue
            header = header_by_col.get(col_index, f"col_{col_index + 1}")
            citation_headers.append(header)
            fragments.append(f"{header}: {normalized}")

        row_blocks.append(
            {
                "page_number": table_page,
                "block_type": "table",
                "role": "tableRow",
                "content": " | ".join(fragments),
                "source_order": table_order + row_index,
                "table_ref": {
                    "table_id": table_id,
                    "row_index": row_index + 1,
                    "headers": citation_headers,
                },
            }
        )

    return row_blocks


def _build_structured_blocks(result: object) -> tuple[list[dict], EventDict]:
    paragraphs = list(getattr(result, "paragraphs", None) or [])
    tables = list(getattr(result, "tables", None) or [])

    role_counts: dict[str, int] = {}
    structured_blocks: list[dict] = []

    for index, paragraph in enumerate(paragraphs):
        role = str(getattr(paragraph, "role", "") or "paragraph")
        role_counts[role] = role_counts.get(role, 0) + 1
        if role in _EXCLUDED_PARAGRAPH_ROLES:
            continue

        content = str(getattr(paragraph, "content", "") or "").strip()
        if not content:
            continue

        structured_blocks.append(
            {
                "page_number": _first_page_number(paragraph),
                "block_type": "paragraph",
                "role": role,
                "content": content,
                "source_order": _first_span_offset(paragraph, fallback=index),
                "table_ref": None,
            }
        )

    total_table_rows = 0
    for index, table in enumerate(tables, start=1):
        table_id = f"T{index}"
        row_blocks = _serialize_table_rows(table, table_id=table_id)
        total_table_rows += len(row_blocks)
        structured_blocks.extend(row_blocks)

    if structured_blocks:
        structured_blocks.sort(key=lambda item: (int(item.get("page_number", 0)), int(item.get("source_order", 0))))

    telemetry: EventDict = {
        "paragraphs_by_role": role_counts,
        "tables_count": len(tables),
        "tables_rows_total": total_table_rows,
        "sections_by_role": role_counts.get("title", 0) + role_counts.get("sectionHeading", 0),
        "sections_by_fallback": 0,
    }
    return structured_blocks, telemetry


class AzureDocumentIntelligenceAdapter(DocumentIntelligencePort):
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def extract_text(self, blob_url: str) -> list[dict]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._api_key),
        )
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=AnalyzeDocumentRequest(url_source=blob_url),
        )
        result = poller.result(timeout=self._timeout_seconds)

        blocks, telemetry = _build_structured_blocks(result)
        if blocks:
            logger.info("document_intelligence_structured_blocks", **telemetry)
            return blocks

        pages: list[dict] = []
        for page in result.pages:
            lines = [line.content for line in page.lines] if page.lines else []
            content = "\n".join(lines).strip()
            if content:
                pages.append({"page_number": int(page.page_number), "content": content, "block_type": "paragraph"})

        if not pages:
            raise DocumentTextExtractionError("No se detectó texto útil en el documento")

        logger.info(
            "document_intelligence_structured_blocks_fallback_lines",
            paragraphs_by_role={},
            tables_count=0,
            tables_rows_total=0,
            sections_by_role=0,
            sections_by_fallback=0,
        )
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
        except Exception as exc:
            is_last_attempt = attempt >= retries
            logger.warning(
                "text_extraction_attempt_failed",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                attempt=attempt,
                retries=retries,
                error=sanitize_error_message(str(exc)),
            )
            if is_last_attempt:
                raise TransientExtractionError(str(exc)) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    raise TransientExtractionError("No se pudo extraer texto")
