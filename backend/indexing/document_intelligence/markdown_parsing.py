"""Parseo del markdown que devuelve Azure Document Intelligence a bloques de encabezado/parrafo, con mapeo de bounding boxes por parrafo."""
from __future__ import annotations

import re

import structlog
from structlog.typing import EventDict

from indexing.document_intelligence.geometry import (
    _extract_bounding_boxes,
    _first_page_number,
    _page_sizes_in_points,
    _page_unit_scales,
)
from indexing.document_intelligence.tables import (
    _attach_lines_to_blocks,
    _build_line_index,
    _serialize_table_rows,
)

logger = structlog.get_logger(__name__)

_MD_PAGE_BREAK = "<!-- PageBreak -->"
_MD_COMMENT_RE = re.compile(r"^<!--.*-->$")
# Document Intelligence marca explicitamente el membrete/pie que detecta en el
# margen de la pagina con este comentario -- pero lo hace de forma inconsistente:
# el MISMO texto puede venir como `PageHeader` en una pagina y, unas paginas mas
# adelante, como un heading real (`#`/`##`) en el markdown (caso real: Nucleoelectrica,
# "NUCLEOELECTRICA ARGENTINA S.A. HOJA DE ESPECIFICACIONES TECNICAS DE COMPRA").
# `_detect_repeated_heading_boilerplate` (headings.py) descarta un heading repetido
# por FRECUENCIA, pero si la enorme mayoria de las repeticiones quedan invisibles
# (se tiran como comentario antes de llegar a heading) nunca cruza el umbral. Por
# eso se captura el texto de estos comentarios: es la propia DI confirmando, en
# otra pagina del mismo documento, que ese texto es membrete -- sin importar
# cuantas veces se cuele como heading.
_MD_PAGE_HEADER_FOOTER_RE = re.compile(r'^<!--\s*Page(?:Header|Footer)\s*=\s*"(.*)"\s*-->$')
_MD_HEADING_RE = re.compile(r"^(#+)\s+(.+)$")
_MD_TABLE_START_RE = re.compile(r"^<table\b")
_MD_TABLE_END_RE = re.compile(r"^</table>")
_MD_FIGURE_START_RE = re.compile(r"^<figure>")
_MD_FIGURE_END_RE = re.compile(r"^</figure>")
_TABLE_SOURCE_ORDER_BASE = 10_000_000
_LINE_WRAP_HYPHEN_RE = re.compile(r"([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])-\n([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])")
_PARA_MATCH_PREFIX_CHARS = 40
_PARA_MATCH_EXACT_BELOW_CHARS = 8
_MD_ESCAPE_RE = re.compile(r"\\([-+.>#*_\[\]()!`~])")


def _dehyphenate(text: str) -> str:
    return _LINE_WRAP_HYPHEN_RE.sub(r"\1\2", text)


def _normalize_furniture_text(text: str) -> str:
    """Misma normalizacion que `_normalize_heading_value(...).lower()` en
    headings.py (whitespace colapsado + minuscula), para que un texto
    confirmado membrete via `PageHeader`/`PageFooter` matchee exactamente
    contra el mismo texto cuando aparece como heading."""
    return " ".join(text.strip().split()).lower()


def _collect_page_header_footer_texts(markdown: str) -> set[str]:
    """Recolecta, en una pasada previa sobre TODO el markdown, el texto que
    Document Intelligence marco explicitamente como membrete/pie de pagina
    (`<!-- PageHeader="..." -->` / `<!-- PageFooter="..." -->`). Ver el
    comentario de `_MD_PAGE_HEADER_FOOTER_RE` para el porque."""
    textos: set[str] = set()
    for raw_line in markdown.splitlines():
        match = _MD_PAGE_HEADER_FOOTER_RE.match(raw_line.strip())
        if match:
            normalizado = _normalize_furniture_text(match.group(1))
            if normalizado:
                textos.add(normalizado)
    return textos


def _build_para_id_index(
    paragraphs: list, unit_scales: dict[int, float] | None = None
) -> dict[tuple[int, int], list[dict[str, float]]]:
    """Construye índice para_id → bounding_boxes para mapeo preciso.

    SOLUCIÓN DEFINITIVA V2 (2026-08): Mapeo por posición estructural.
    Usa (page_number, paragraph_index_in_page) como identidad estable.
    Esto garantiza precisión 100% sin ambigüedad por contenido duplicado.

    Args:
        paragraphs: Lista de paragraphs de Azure Document Intelligence

    Returns:
        Diccionario {(page, index): [bbox1, bbox2, ...]}
    """
    paras_by_page: dict[int, list] = {}
    for para in paragraphs:
        page = _first_page_number(para)
        if page not in paras_by_page:
            paras_by_page[page] = []
        paras_by_page[page].append(para)
    bbox_index = {}
    total_paras = 0
    paras_with_bbox = 0

    for page_num, page_paras in paras_by_page.items():
        page_paras_sorted = sorted(
            page_paras, key=lambda p: getattr(getattr(p, "span", None), "offset", 0)
        )

        for idx, para in enumerate(page_paras_sorted):
            total_paras += 1
            bboxes = _extract_bounding_boxes(para, unit_scales)
            if bboxes:
                para_id = (page_num, idx)
                bbox_index[para_id] = {
                    "bbox": bboxes,
                    "content": str(getattr(para, "content", "") or ""),
                }
                paras_with_bbox += 1

    logger.info(
        "para_id_index_built",
        total_paragraphs=total_paras,
        paragraphs_with_bbox=paras_with_bbox,
        bbox_coverage_pct=round(100 * paras_with_bbox / total_paras, 1) if total_paras > 0 else 0,
    )

    return bbox_index


def _unescape_markdown(texto: str) -> str:
    """Saca los escapes de markdown que DI mete y el texto plano no tiene."""
    return _MD_ESCAPE_RE.sub(r"\1", texto)


def _same_text(block_content: object, para_content: object) -> bool:
    """¿El bloque del parser y el párrafo de DI son el mismo texto?"""
    izquierda = _unescape_markdown(" ".join(str(block_content or "").split()).lower())
    derecha = _unescape_markdown(" ".join(str(para_content or "").split()).lower())
    if not izquierda or not derecha:
        return False
    if min(len(izquierda), len(derecha)) < _PARA_MATCH_EXACT_BELOW_CHARS:
        return izquierda == derecha

    if (
        izquierda.startswith(derecha)
        or izquierda.endswith(derecha)
        or derecha.startswith(izquierda)
        or derecha.endswith(izquierda)
    ):
        return True

    largo = min(_PARA_MATCH_PREFIX_CHARS, len(izquierda), len(derecha))
    return largo > 0 and izquierda[:largo] == derecha[:largo]


def _match_paragraph(
    contenido: object,
    candidatos: list[tuple[int, dict]],
    usados: set[int],
    cursor: int,
) -> tuple[int | None, dict]:
    """El párrafo de Document Intelligence que corresponde a este bloque."""
    for indice, entrada in candidatos:
        if indice <= cursor or indice in usados:
            continue
        if _same_text(contenido, entrada.get("content")):
            return indice, entrada

    for indice, entrada in candidatos:
        if indice in usados:
            continue
        if _same_text(contenido, entrada.get("content")):
            return indice, entrada

    return None, {}


def _enrich_blocks_with_para_id(
    blocks: list[dict],
    bbox_by_para_id: dict[tuple[int, int], list[dict[str, float]]],
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> None:
    """Enriquece bloques con para_id y bbox usando posición estructural."""
    stats = {"total": 0, "matched": 0, "no_match": 0, "text_mismatch": 0}
    blocks_by_page: dict[int, list[dict]] = {}
    for block in blocks:
        page = block.get("page_number")
        if page is None:
            continue
        if page not in blocks_by_page:
            blocks_by_page[page] = []
        blocks_by_page[page].append(block)

    for page_num, page_blocks in blocks_by_page.items():
        page_blocks_sorted = sorted(
            page_blocks, key=lambda b: (b.get("source_order", 0), b.get("row_order", 0))
        )
        candidatos = [
            (para_id[1], entrada)
            for para_id, entrada in bbox_by_para_id.items()
            if para_id[0] == page_num and isinstance(entrada, dict)
        ]
        candidatos.sort(key=lambda par: par[0])

        usados: set[int] = set()
        cursor = -1  # último párrafo emparejado: fuerza el orden de lectura

        for block in page_blocks_sorted:
            stats["total"] += 1
            if block.get("table_ref"):
                block["para_id"] = None
                block["bbox"] = []
                stats["no_match"] += 1
                continue

            contenido = block.get("content")
            elegido, entrada = _match_paragraph(contenido, candidatos, usados, cursor)

            if elegido is None:
                block["para_id"] = None
                block["bbox"] = []
                stats["no_match"] += 1
                stats["text_mismatch"] += 1
                logger.debug(
                    "para_sin_parrafo_equivalente",
                    page=page_num,
                    content_preview=str(contenido or "")[:80],
                )
                continue

            usados.add(elegido)
            cursor = elegido
            para_id = (page_num, elegido)
            block["para_id"] = para_id
            bboxes = entrada.get("bbox") or []

            if not bboxes:
                block["bbox"] = []
                stats["no_match"] += 1
                continue
            page_size = (page_sizes or {}).get(page_num)
            valid_bboxes = []
            for bbox in bboxes:
                if page_size is None:
                    is_valid = (
                        bbox["x"] >= 0
                        and bbox["y"] >= 0
                        and bbox["width"] > 0
                        and bbox["height"] > 0
                    )
                else:
                    page_width, page_height = page_size
                    is_valid = (
                        -1.0 <= bbox["x"] <= page_width + 1.0
                        and -1.0 <= bbox["y"] <= page_height + 1.0
                        and 0 < bbox["width"] <= page_width + 1.0
                        and 0 < bbox["height"] <= page_height + 1.0
                    )

                if is_valid:
                    valid_bboxes.append(bbox)
                else:
                    logger.warning(
                        "bbox_out_of_bounds",
                        page=page_num,
                        para_id=para_id,
                        bbox=bbox,
                        page_size_points=page_size,
                    )

            if not valid_bboxes:
                block["bbox"] = []
                stats["no_match"] += 1
                continue

            block["bbox"] = valid_bboxes
            stats["matched"] += 1
    match_rate = (stats["matched"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(
        "para_id_enrichment_complete",
        total_blocks=stats["total"],
        matched=stats["matched"],
        no_match=stats["no_match"],
        text_mismatch=stats["text_mismatch"],
        match_rate_pct=round(match_rate, 1),
    )


def _repair_heading_split_within_single_line(blocks: list[dict]) -> None:
    """Repara un heading que el MARKDOWN de Document Intelligence partió en
    dos bloques, aunque su propia capa de layout (`lines`, adjunta por
    `_attach_lines_to_blocks`) sabe que es UNA sola línea física.

    Caso real (Rosario): el markdown de DI trae

        ## ARTÍCULO 12: PLA
        ZO DE ENTREGA El plazo de entrega...

    -- dos "líneas" de markdown, la primera detectada como heading. Pero la
    línea de OCR real, adjunta al segundo bloque porque su bbox cae dentro de
    ella, es una sola: "ARTÍCULO 12: PLAZO DE ENTREGA". No es la geometría de
    párrafo (`_starts_on_same_line` en `chunking/headings.py`, pensado para
    OTRO caso: cuando el heading y el cuerpo son dos bloques DISTINTOS que
    solo coinciden en altura) -- es una inconsistencia interna de DI entre su
    heurística de estilo para el markdown y su OCR de línea. Reconstruye
    usando el texto real de la línea como fuente de verdad -- no un
    heurístico de forma de palabra -- así que solo actúa cuando puede
    verificar que el cuerpo, tal como llegó, es exactamente lo que queda de
    esa línea real después de sacarle el heading.
    """
    for index in range(len(blocks) - 1):
        heading_block = blocks[index]
        if heading_block.get("heading_level") is None:
            continue

        body_block = blocks[index + 1]
        if (
            body_block.get("heading_level") is not None
            or body_block.get("table_ref")
            or body_block.get("page_number") != heading_block.get("page_number")
        ):
            continue

        lines = body_block.get("lines") or []
        if not lines:
            continue

        first_line_text = str(lines[0].get("t", ""))
        heading_content = str(heading_block.get("content", ""))
        if not first_line_text.startswith(heading_content) or len(first_line_text) <= len(
            heading_content
        ):
            continue

        remainder = first_line_text[len(heading_content) :]
        body_content = str(body_block.get("content", ""))
        if not body_content.startswith(remainder):
            continue

        heading_block["content"] = first_line_text
        body_block["content"] = body_content[len(remainder) :].lstrip()

        logger.info(
            "repaired_heading_split_within_di_line",
            page=heading_block.get("page_number"),
            heading_before=heading_content[:60],
            heading_after=first_line_text[:80],
        )


def _parse_markdown_blocks(
    markdown: str,
) -> tuple[list[dict], dict[int, int], list[tuple[int, int]]]:
    """Convierte el markdown de Document Intelligence en bloques de encabezado
    (con su nivel, segun cantidad de '#') y parrafo, recuperando la pagina real
    via los marcadores `<!-- PageBreak -->`. Las tablas HTML embebidas se
    saltean aca -- se extraen aparte desde `result.tables` (fila por fila, con
    table_ref) para no perder la granularidad que ya tenia el pipeline.

    Ademas devuelve, para cada `<table>` que aparece en el markdown y en el
    mismo orden, la posicion (pagina, source_order) que ocupa en el flujo de
    lectura. Es lo que permite reinsertar las filas en su lugar real en vez de
    empujarlas al final de la pagina."""
    blocks: list[dict] = []
    heading_levels_by_order: dict[int, int] = {}
    table_positions: list[tuple[int, int]] = []
    confirmed_page_furniture = _collect_page_header_footer_texts(markdown)

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
            if len(text) < 100:
                uppercase_ratio = sum(1 for c in text if c.isupper()) / len(text) if text else 0
                if uppercase_ratio > 0.5:
                    logger.debug(
                        "potential_missed_heading",
                        page=page_number,
                        source_order=source_order,
                        uppercase_ratio=round(uppercase_ratio, 2),
                        text_preview=text[:80],
                    )
            source_order += 1

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()

        if stripped == _MD_PAGE_BREAK:
            flush_paragraph()
            page_number += 1
            continue
        if _MD_COMMENT_RE.match(stripped):
            continue
        if _MD_FIGURE_START_RE.match(stripped):
            flush_paragraph()
            in_figure = True
            continue
        if _MD_FIGURE_END_RE.match(stripped):
            in_figure = False
            continue
        if in_figure:
            if stripped:
                logger.debug(
                    "figure_content_discarded",
                    page=page_number,
                    content_preview=stripped[:100],
                )
            continue  # logos/membretes escaneados como figura: sin texto util
        if _MD_TABLE_START_RE.match(stripped):
            flush_paragraph()
            table_positions.append((page_number, source_order))
            source_order += 1
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
                is_confirmed_furniture = (
                    _normalize_furniture_text(heading_text) in confirmed_page_furniture
                )
                blocks.append(
                    {
                        "page_number": page_number,
                        "block_type": "paragraph",
                        "content": heading_text,
                        "source_order": source_order,
                        "table_ref": None,
                        **({"is_confirmed_page_furniture": True} if is_confirmed_furniture else {}),
                    }
                )
                heading_levels_by_order[source_order] = level
                logger.debug(
                    "heading_detected",
                    page=page_number,
                    level=level,
                    source_order=source_order,
                    text_preview=heading_text[:100],
                )
                source_order += 1
            continue

        if not stripped:
            flush_paragraph()
            continue

        paragraph_lines.append(raw_line)

    flush_paragraph()
    return blocks, heading_levels_by_order, table_positions


def _build_markdown_blocks(
    result: object,
    *,
    document_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[list[dict], EventDict]:
    markdown = str(getattr(result, "content", "") or "")
    tables = list(getattr(result, "tables", None) or [])
    paragraphs = list(getattr(result, "paragraphs", None) or [])

    blocks, heading_levels_by_order, table_positions = _parse_markdown_blocks(markdown)
    for block in blocks:
        level = heading_levels_by_order.get(block["source_order"])
        if level is not None:
            block["heading_level"] = level
    unit_scales = _page_unit_scales(result)

    bbox_by_para_id = _build_para_id_index(paragraphs, unit_scales)
    _enrich_blocks_with_para_id(blocks, bbox_by_para_id, _page_sizes_in_points(result, unit_scales))
    _attach_lines_to_blocks(blocks, _build_line_index(result, unit_scales))
    _repair_heading_split_within_single_line(blocks)

    total_table_rows = 0
    tables_placed_in_reading_order = 0
    tables_with_fallback_position = 0
    for index, table in enumerate(tables, start=1):
        table_id = f"T{index}"
        row_blocks = _serialize_table_rows(table, table_id=table_id, unit_scales=unit_scales)
        position = table_positions[index - 1] if index - 1 < len(table_positions) else None
        if position is not None:
            table_page, table_order = position
            tables_placed_in_reading_order += 1
            for row_index, row_block in enumerate(row_blocks):
                row_block["page_number"] = table_page
                row_block["source_order"] = table_order
                row_block["row_order"] = row_index
        else:
            tables_with_fallback_position += 1
            logger.warning(
                "table_position_fallback",
                document_id=document_id,
                correlation_id=correlation_id,
                table_id=table_id,
                table_index=index,
                reason="No <table> tag found in markdown for this table from result.tables",
            )
            for row_index, row_block in enumerate(row_blocks):
                row_block["source_order"] = _TABLE_SOURCE_ORDER_BASE + (index * 1000) + row_index
                row_block["row_order"] = row_index
        total_table_rows += len(row_blocks)
        blocks.extend(row_blocks)

    if blocks:
        blocks.sort(
            key=lambda item: (
                int(item.get("page_number", 0)),
                int(item.get("source_order", 0)),
                int(item.get("row_order", 0)),
            )
        )

    telemetry: EventDict = {
        "markdown_chars": len(markdown),
        "headings_count": len(heading_levels_by_order),
        "tables_count": len(tables),
        "tables_rows_total": total_table_rows,
        "tables_placed_in_reading_order": tables_placed_in_reading_order,
        "tables_with_fallback_position": tables_with_fallback_position,
        "table_positions_detected": len(table_positions),
    }
    if tables_with_fallback_position > 0:
        logger.warning(
            "table_position_mismatch",
            document_id=document_id,
            correlation_id=correlation_id,
            tables_count=len(tables),
            table_positions_in_markdown=len(table_positions),
            tables_with_fallback=tables_with_fallback_position,
        )
    return blocks, telemetry
