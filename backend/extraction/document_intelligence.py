from __future__ import annotations

import re
from time import sleep
from uuid import UUID

import structlog
from structlog.typing import EventDict

from extraction.errors import DocumentTextExtractionError, TransientExtractionError
from extraction.ports.document_intelligence_port import DocumentIntelligencePort
from shared.config import get_settings
from shared.security import sanitize_error_message, sanitize_url_for_logs

logger = structlog.get_logger(__name__)

# Document Intelligence, en modo markdown, marca cada salto de pagina con este
# comentario literal -- es la unica forma confiable de recuperar el numero de
# pagina, porque el `<!-- PageNumber="N de M" -->` que a veces lo acompana no
# siempre esta presente (depende de si el pie de pagina real del documento
# tiene forma "N de M").
_MD_PAGE_BREAK = "<!-- PageBreak -->"
_MD_COMMENT_RE = re.compile(r"^<!--.*-->$")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_MD_TABLE_START_RE = re.compile(r"^<table\b")
_MD_TABLE_END_RE = re.compile(r"^</table>")
_MD_FIGURE_START_RE = re.compile(r"^<figure>")
_MD_FIGURE_END_RE = re.compile(r"^</figure>")
# Empuja las filas de tabla (extraidas aparte de result.tables, no del texto
# markdown) siempre despues de los bloques de texto de su misma pagina. No hay
# un sistema de offsets comun entre el markdown reconstruido y los spans que
# Azure calcula sobre el documento original, asi que en vez de tratar de
# interpolar exactamente se aprovecha que en la practica el texto que
# introduce una tabla siempre viene antes que la tabla misma.
_TABLE_SOURCE_ORDER_BASE = 10_000_000
# Une palabras partidas por un salto de linea con guion de fin de renglon
# ("ad-\nquisicion" -> "adquisicion"). Solo aplica entre minusculas: un guion
# real de palabra compuesta casi siempre separa dos palabras completas, no
# deja una letra sola pegada al salto de linea.
_LINE_WRAP_HYPHEN_RE = re.compile(r"([a-záéíóúñ])-\n([a-záéíóúñ])")


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


def _dehyphenate(text: str) -> str:
    return _LINE_WRAP_HYPHEN_RE.sub(r"\1\2", text)


def _parse_markdown_blocks(markdown: str) -> tuple[list[dict], dict[int, int]]:
    """Convierte el markdown de Document Intelligence en bloques de encabezado
    (con su nivel, segun cantidad de '#') y parrafo, recuperando la pagina real
    via los marcadores `<!-- PageBreak -->`. Las tablas HTML embebidas se
    saltean aca -- se extraen aparte desde `result.tables` (fila por fila, con
    table_ref) para no perder la granularidad que ya tenia el pipeline."""
    blocks: list[dict] = []
    heading_levels_by_order: dict[int, int] = {}

    page_number = 1
    source_order = 0
    paragraph_lines: list[str] = []
    in_figure = False
    in_table = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines, source_order
        text = _dehyphenate("\n".join(paragraph_lines)).strip()
        paragraph_lines = []
        if text:
            blocks.append(
                {
                    "page_number": page_number,
                    "block_type": "paragraph",
                    "content": text,
                    "source_order": source_order,
                    "table_ref": None,
                }
            )
            source_order += 1

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()

        if stripped == _MD_PAGE_BREAK:
            flush_paragraph()
            page_number += 1
            continue
        if _MD_COMMENT_RE.match(stripped):
            # <!-- PageNumber=... / PageFooter=... / PageHeader=... --> son
            # membrete/pie repetido que Azure ya separa del cuerpo: se descarta,
            # no hace falta la deteccion de boilerplate por repeticion de antes.
            continue
        if _MD_FIGURE_START_RE.match(stripped):
            in_figure = True
            continue
        if _MD_FIGURE_END_RE.match(stripped):
            in_figure = False
            continue
        if in_figure:
            continue  # logos/membretes escaneados como figura: sin texto util
        if _MD_TABLE_START_RE.match(stripped):
            flush_paragraph()
            in_table = True
            continue
        if _MD_TABLE_END_RE.match(stripped):
            in_table = False
            continue
        if in_table:
            continue

        heading_match = _MD_HEADING_RE.match(stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            if heading_text:
                blocks.append(
                    {
                        "page_number": page_number,
                        "block_type": "paragraph",
                        "content": heading_text,
                        "source_order": source_order,
                        "table_ref": None,
                    }
                )
                heading_levels_by_order[source_order] = level
                source_order += 1
            continue

        if not stripped:
            if paragraph_lines:
                paragraph_lines.append("")
            continue

        paragraph_lines.append(raw_line)

    flush_paragraph()
    return blocks, heading_levels_by_order


def _build_markdown_blocks(result: object) -> tuple[list[dict], EventDict]:
    markdown = str(getattr(result, "content", "") or "")
    tables = list(getattr(result, "tables", None) or [])

    blocks, heading_levels_by_order = _parse_markdown_blocks(markdown)
    for block in blocks:
        level = heading_levels_by_order.get(block["source_order"])
        if level is not None:
            block["heading_level"] = level

    total_table_rows = 0
    for index, table in enumerate(tables, start=1):
        table_id = f"T{index}"
        row_blocks = _serialize_table_rows(table, table_id=table_id)
        for row_index, row_block in enumerate(row_blocks):
            row_block["source_order"] = _TABLE_SOURCE_ORDER_BASE + (index * 1000) + row_index
        total_table_rows += len(row_blocks)
        blocks.extend(row_blocks)

    if blocks:
        blocks.sort(key=lambda item: (int(item.get("page_number", 0)), int(item.get("source_order", 0))))

    telemetry: EventDict = {
        "markdown_chars": len(markdown),
        "headings_count": len(heading_levels_by_order),
        "tables_count": len(tables),
        "tables_rows_total": total_table_rows,
    }
    return blocks, telemetry


class AzureDocumentIntelligenceAdapter(DocumentIntelligencePort):
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def extract_text(self, blob_url: str) -> list[dict]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._api_key),
        )
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=AnalyzeDocumentRequest(url_source=blob_url),
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        result = poller.result(timeout=self._timeout_seconds)

        blocks, telemetry = _build_markdown_blocks(result)
        if not blocks:
            raise DocumentTextExtractionError("No se detectó texto útil en el documento")

        logger.info("document_intelligence_markdown_blocks", **telemetry)
        return blocks


def _build_adapter() -> DocumentIntelligencePort:
    settings = get_settings()
    if settings.is_development:
        from extraction.local.markitdown_extraction import MarkItDownAdapter

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
