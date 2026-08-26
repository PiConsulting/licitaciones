"""Serializacion de tablas de Azure Document Intelligence a filas indexables, y el indice de renglones por bloque."""
from __future__ import annotations

from typing import Any

import structlog

from indexing.document_intelligence.geometry import (
    _extract_bounding_boxes,
    _first_page_number,
    _RegionDeRenglon,
    _safe_int,
    _renglon_dentro_de,
)

logger = structlog.get_logger(__name__)


def _build_line_index(
    result: object, unit_scales: dict[int, float] | None = None
) -> dict[int, list[dict[str, Any]]]:
    """Geometría por RENGLÓN de cada página, en puntos."""
    index: dict[int, list[dict[str, Any]]] = {}
    for page in list(getattr(result, "pages", None) or []):
        page_number = _safe_int(getattr(page, "page_number", None), default=0)
        if page_number <= 0:
            continue
        renglones: list[dict[str, Any]] = []
        for line in list(getattr(page, "lines", None) or []):
            contenido = str(getattr(line, "content", "") or "").strip()
            if not contenido:
                continue
            caja = _extract_bounding_boxes(
                _RegionDeRenglon(page_number, getattr(line, "polygon", None)), unit_scales
            )
            if not caja:
                continue
            renglon = dict(caja[0])
            renglon.pop("page", None)
            renglon["t"] = contenido
            renglones.append(renglon)
        if renglones:
            renglones.sort(key=lambda r: (round(r["y"], 1), r["x"]))
            index[page_number] = renglones
    return index


def _attach_lines_to_blocks(
    blocks: list[dict], line_index: dict[int, list[dict[str, Any]]]
) -> None:
    """Cuelga de cada bloque los renglones que caen dentro de su bbox (HL-09)."""
    if not line_index:
        return

    for block in blocks:
        cajas = [caja for caja in (block.get("bbox") or []) if isinstance(caja, dict)]
        if not cajas:
            continue
        adentro: list[dict[str, Any]] = []
        for caja in cajas:
            pagina = _safe_int(caja.get("page"), default=0)
            for renglon in line_index.get(pagina, []):
                if _renglon_dentro_de(renglon, caja) and renglon not in adentro:
                    adentro.append(renglon)
        if adentro:
            block["lines"] = adentro


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


def _serialize_table_rows(
    table: object, table_id: str, unit_scales: dict[int, float] | None = None
) -> list[dict]:
    row_count = _safe_int(getattr(table, "row_count", 0), default=0)
    column_count = _safe_int(getattr(table, "column_count", 0), default=0)
    cells = list(getattr(table, "cells", None) or [])

    if row_count <= 0:
        row_count = (
            max((_safe_int(getattr(cell, "row_index", 0), default=0) for cell in cells), default=-1)
            + 1
        )
    if column_count <= 0:
        column_count = (
            max(
                (_safe_int(getattr(cell, "column_index", 0), default=0) for cell in cells),
                default=-1,
            )
            + 1
        )

    if row_count <= 0 or column_count <= 0:
        return []

    matrix = [["" for _ in range(column_count)] for _ in range(row_count)]
    header_by_col: dict[int, str] = {}
    header_rows: set[int] = set()
    bboxes_by_row: dict[int, list] = {}

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
        cell_bboxes = _extract_bounding_boxes(cell, unit_scales)
        if cell_bboxes:
            if row_index not in bboxes_by_row:
                bboxes_by_row[row_index] = []
            bboxes_by_row[row_index].extend(cell_bboxes)

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
        content_fragments: list[str] = []
        citation_headers: list[str] = []

        for col_index, cell_value in enumerate(row):
            normalized = cell_value.strip()
            if not normalized:
                continue
            header = header_by_col.get(col_index, f"col_{col_index + 1}")
            citation_headers.append(header)
            content_fragments.append(f"{header}: {normalized}")

        row_blocks.append(
            {
                "page_number": table_page,
                "block_type": "table",
                "role": "tableRow",
                "content": "\n".join(content_fragments),  # Formato limpio, una línea por campo
                "source_order": table_order + row_index,
                "table_ref": {
                    "table_id": table_id,
                    "row_index": row_index + 1,
                    "headers": citation_headers,
                },
                "bbox": bboxes_by_row.get(row_index, []),  # Bbox de todas las celdas de esta fila
            }
        )

    return row_blocks
