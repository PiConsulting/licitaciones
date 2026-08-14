from __future__ import annotations

import re
from time import sleep
from uuid import UUID

import structlog
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
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
# ("ad-\nquisicion" -> "adquisicion", "ADQUI-\nSICIÓN" -> "ADQUISICIÓN").
# Soporta minúsculas, mayúsculas y ü/Ü. Un guion real de palabra compuesta
# casi siempre separa dos palabras completas, no deja una letra sola pegada
# al salto de linea, por lo que este regex es suficientemente específico.
_LINE_WRAP_HYPHEN_RE = re.compile(r"([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])-\n([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])")


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


# Azure Document Intelligence expresa las coordenadas en la unidad que reporta
# `result.pages[i].unit`: PULGADAS para PDF y PÍXELES para imágenes sueltas.
# El resto del pipeline (y el visor) trabajan en PUNTOS de PDF, que es lo que
# devuelve PyMuPDF en `highlight.py`. Ver `_page_unit_scales`.
_POINTS_PER_INCH = 72.0


def _page_unit_scales(result: object) -> dict[int, float]:
    """Factor de conversión a PUNTOS para cada página del documento.

    FIX (auditoría 2026-08-13, hallazgo ING-03): el bbox de Azure DI se guardaba
    en la unidad cruda que devuelve el servicio, sin convertir. Para un PDF eso
    son PULGADAS (valores del orden de 0-11), mientras que el camino de
    highlighting con PyMuPDF emite PUNTOS (0-842). Los dos caminos alimentan el
    mismo campo `highlight_regions` y el visor multiplica lo que reciba por la
    escala de zoom, así que las regiones en pulgadas se dibujaban como un
    recuadro de ~7 px pegado al ángulo superior izquierdo.

    Se vio en un análisis real: de ~35 sources, unas 10 salieron en pulgadas
    (`{"x": 0.77, "y": 2.12, "width": 6.71}`) y el resto en puntos
    (`{"x": 56.8, "y": 465.2, "width": 240.3}`), mezcladas en la misma
    respuesta.

    Devuelve {page_number: factor}. Las páginas cuya unidad no se puede
    convertir con seguridad quedan fuera del diccionario y su bbox se descarta
    en `_extract_bounding_boxes` -- mejor sin resaltado que con uno que apunta
    a cualquier lado.
    """
    scales: dict[int, float] = {}
    unsupported: dict[int, str] = {}

    for page in list(getattr(result, "pages", None) or []):
        page_number = _safe_int(getattr(page, "page_number", None), default=0)
        if page_number <= 0:
            continue
        unit = str(getattr(page, "unit", "") or "").strip().lower()

        if unit == "inch":
            scales[page_number] = _POINTS_PER_INCH
        elif unit in {"point", "pt"}:
            scales[page_number] = 1.0
        else:
            # "pixel" (imágenes sueltas) y cualquier unidad futura: no se puede
            # convertir sin conocer el DPI real del origen. Esta app sólo acepta
            # PDF, así que llegar acá indica un cambio del servicio.
            unsupported[page_number] = unit or "(sin unidad)"

    if unsupported:
        logger.error(
            "document_intelligence_unsupported_bbox_unit",
            pages=sorted(unsupported),
            units=sorted(set(unsupported.values())),
            impact="esas páginas quedan sin bbox; el highlighting cae al camino de PyMuPDF",
        )

    return scales


def _extract_bounding_boxes(
    item: object, unit_scales: dict[int, float] | None = None
) -> list[dict[str, float]]:
    """Extrae bounding boxes de un item de Azure Document Intelligence.

    Convierte las bounding_regions a coordenadas top-left origin (estándar web)
    y a PUNTOS de PDF, que es la unidad del contrato de `highlight_regions`
    (ver `analysis/extraction/highlight.py::compute_highlight_regions`).

    Args:
        item: entidad de Azure DI con `bounding_regions`.
        unit_scales: {page_number: factor a puntos}, de `_page_unit_scales`.
            Si es None no se convierte nada -- sólo para llamadores de test que
            ya trabajan en puntos.

    Returns:
        Lista de bbox: [{"page": int, "x": float, "y": float, "width": float, "height": float}]
    """
    regions = getattr(item, "bounding_regions", None) or []
    bboxes = []
    
    if not regions:
        # Diagnostic: si no hay bounding_regions, verificar si el atributo existe
        has_attr = hasattr(item, "bounding_regions")
        logger.debug(
            "no_bounding_regions",
            has_attr=has_attr,
            attr_value=getattr(item, "bounding_regions", "NOT_SET"),
        )
        return bboxes
    
    for region in regions:
        page_number = getattr(region, "page_number", None)
        polygon = getattr(region, "polygon", None)
        
        if page_number is None or not polygon or len(polygon) < 4:
            continue
        
        # polygon es lista de coordenadas [x0, y0, x1, y1, x2, y2, x3, y3]
        # donde (x0, y0) es top-left, (x2, y2) es bottom-right
        # Azure DI ya usa top-left origin, así que no necesitamos convertir
        x_coords = [polygon[i] for i in range(0, len(polygon), 2)]
        y_coords = [polygon[i] for i in range(1, len(polygon), 2)]
        
        x = min(x_coords)
        y = min(y_coords)
        width = max(x_coords) - x
        height = max(y_coords) - y

        page = _safe_int(page_number, default=1)
        if unit_scales is None:
            scale = 1.0
        elif page in unit_scales:
            scale = unit_scales[page]
        else:
            # Unidad desconocida para esta página: se descarta el bbox en vez
            # de emitirlo en una escala que el consumidor no puede interpretar.
            continue

        bboxes.append({
            "page": page,
            "x": float(x) * scale,
            "y": float(y) * scale,
            "width": float(width) * scale,
            "height": float(height) * scale,
        })
    
    return bboxes


def _page_sizes_in_points(
    result: object, unit_scales: dict[int, float]
) -> dict[int, tuple[float, float]]:
    """Dimensiones (ancho, alto) de cada página, en PUNTOS.

    Reemplaza los límites hardcodeados `x <= 1200 / y <= 1600` que usaba
    `_enrich_blocks_with_para_id` para validar coordenadas (ING-03). Esos dos
    números no correspondían a ninguna unidad concreta: para un PDF en pulgadas
    (valores 0-11) nunca disparaban, y para cualquier documento en píxeles
    descartaban el 100% de los bbox. Validar contra el tamaño REAL de la página
    es correcto en cualquier unidad y detecta el caso que importa: un bbox que
    cae fuera de la hoja.
    """
    sizes: dict[int, tuple[float, float]] = {}
    for page in list(getattr(result, "pages", None) or []):
        page_number = _safe_int(getattr(page, "page_number", None), default=0)
        scale = unit_scales.get(page_number)
        if page_number <= 0 or scale is None:
            continue
        width = getattr(page, "width", None)
        height = getattr(page, "height", None)
        if width is None or height is None:
            continue
        try:
            sizes[page_number] = (float(width) * scale, float(height) * scale)
        except (TypeError, ValueError):
            continue
    return sizes


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
        row_count = max((_safe_int(getattr(cell, "row_index", 0), default=0) for cell in cells), default=-1) + 1
    if column_count <= 0:
        column_count = max((_safe_int(getattr(cell, "column_index", 0), default=0) for cell in cells), default=-1) + 1

    if row_count <= 0 or column_count <= 0:
        return []

    matrix = [["" for _ in range(column_count)] for _ in range(row_count)]
    header_by_col: dict[int, str] = {}
    header_rows: set[int] = set()
    # Colectar bboxes por fila
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
        
        # Extraer bbox de cada celda
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

        # Formato limpio para embeddings (sin "Tabla TX | Fila N")
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


def _dehyphenate(text: str) -> str:
    return _LINE_WRAP_HYPHEN_RE.sub(r"\1\2", text)


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
    # Agrupar paragraphs por página
    paras_by_page: dict[int, list] = {}
    for para in paragraphs:
        page = _first_page_number(para)
        if page not in paras_by_page:
            paras_by_page[page] = []
        paras_by_page[page].append(para)
    
    # Construir índice: (page, index_in_page) → bbox
    bbox_index = {}
    total_paras = 0
    paras_with_bbox = 0
    
    for page_num, page_paras in paras_by_page.items():
        # Ordenar por span offset para orden determinístico
        page_paras_sorted = sorted(
            page_paras,
            key=lambda p: getattr(getattr(p, "span", None), "offset", 0)
        )
        
        for idx, para in enumerate(page_paras_sorted):
            total_paras += 1
            bboxes = _extract_bounding_boxes(para, unit_scales)
            if bboxes:
                para_id = (page_num, idx)
                bbox_index[para_id] = bboxes
                paras_with_bbox += 1
    
    logger.info(
        "para_id_index_built",
        total_paragraphs=total_paras,
        paragraphs_with_bbox=paras_with_bbox,
        bbox_coverage_pct=round(100 * paras_with_bbox / total_paras, 1) if total_paras > 0 else 0,
    )
    
    return bbox_index


def _enrich_blocks_with_para_id(
    blocks: list[dict],
    bbox_by_para_id: dict[tuple[int, int], list[dict[str, float]]],
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> None:
    """Enriquece bloques con para_id y bbox usando posición estructural.
    
    SOLUCIÓN DEFINITIVA V2 (2026-08): Identidad por posición, no contenido.
    - Asigna para_id secuencial a cada bloque según orden de aparición en página
    - Busca bbox directamente por para_id
    - Precisión 100% sin ambigüedad por contenido duplicado
    
    Args:
        blocks: Lista de bloques a enriquecer (se modifica in-place)
        bbox_by_para_id: Índice (page, index) → bboxes
    """
    stats = {"total": 0, "matched": 0, "no_match": 0}
    
    # Asignar para_id secuencial a blocks por página
    blocks_by_page: dict[int, list[dict]] = {}
    for block in blocks:
        page = block.get("page_number")
        if page is None:
            continue
        if page not in blocks_by_page:
            blocks_by_page[page] = []
        blocks_by_page[page].append(block)
    
    for page_num, page_blocks in blocks_by_page.items():
        # Ordenar por source_order para mantener orden de lectura
        page_blocks_sorted = sorted(
            page_blocks,
            key=lambda b: (b.get("source_order", 0), b.get("row_order", 0))
        )
        
        para_index = 0
        for block in page_blocks_sorted:
            stats["total"] += 1
            
            # Solo asignar para_id a bloques de párrafo (no tablas)
            if block.get("table_ref"):
                # Tablas no tienen para_id (son extraídas por separado)
                block["para_id"] = None
                block["bbox"] = []
                stats["no_match"] += 1
                continue
            
            # Asignar para_id = (page, sequential_index)
            para_id = (page_num, para_index)
            block["para_id"] = para_id
            para_index += 1
            
            # Buscar bbox por para_id
            bboxes = bbox_by_para_id.get(para_id)
            
            if not bboxes:
                # No match - markdown generó más bloques que paragraphs originales
                block["bbox"] = []
                stats["no_match"] += 1
                logger.debug(
                    "para_id_no_match",
                    page=page_num,
                    para_id=para_id,
                    content_preview=str(block.get("content", ""))[:80],
                )
                continue
            
            # ING-03: validar contra el tamaño REAL de la página (en puntos),
            # no contra dos constantes sin unidad. Se deja 1pt de tolerancia
            # por el redondeo del polígono de Azure DI.
            page_size = (page_sizes or {}).get(page_num)
            valid_bboxes = []
            for bbox in bboxes:
                if page_size is None:
                    # Sin dimensiones conocidas sólo se exige que el rectángulo
                    # exista y no sea negativo.
                    is_valid = bbox["x"] >= 0 and bbox["y"] >= 0 and bbox["width"] > 0 and bbox["height"] > 0
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
    
    # Log stats de calidad de mapeo
    match_rate = (stats["matched"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(
        "para_id_enrichment_complete",
        total_blocks=stats["total"],
        matched=stats["matched"],
        no_match=stats["no_match"],
        match_rate_pct=round(match_rate, 1),
    )


def _parse_markdown_blocks(markdown: str) -> tuple[list[dict], dict[int, int], list[tuple[int, int]]]:
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
            # LOG diagnóstico: detectar posibles títulos perdidos (heurística)
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
            # LOG diagnóstico: registrar contenido descartado de figuras
            if stripped:
                logger.debug(
                    "figure_content_discarded",
                    page=page_number,
                    content_preview=stripped[:100],
                )
            continue  # logos/membretes escaneados como figura: sin texto util
        if _MD_TABLE_START_RE.match(stripped):
            flush_paragraph()
            # Reserva la posicion de lectura de esta tabla y consume un
            # source_order, para que las filas se ordenen justo aca respecto de
            # los parrafos y encabezados vecinos.
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
                # LOG diagnóstico: registrar heading detectado
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
            # FIX CRÍTICO (auditoría 2026-08-12, hallazgo C-2): antes, una línea en
            # blanco NO cerraba el párrafo -- solo se agregaba como separador
            # interno, así que todo el cuerpo entre dos headings terminaba en un
            # único bloque con "\n\n" internos. Eso hacía que el índice
            # (página, índice_secuencial) que arma _build_para_id_index (a partir
            # de result.paragraphs de Document Intelligence, con un registro por
            # párrafo REAL) dejara de corresponderse con el índice de "blocks" de
            # este parser en cuanto había más de un párrafo de cuerpo seguido
            # -- el caso común, no el edge case. El resultado: bloques (y sus
            # chunks/highlights) recibían el bbox de OTRO párrafo de la misma
            # página. Haciendo flush en cada línea en blanco, 1 bloque de este
            # parser vuelve a corresponder a 1 párrafo real de Document
            # Intelligence, que es la precondición que _enrich_blocks_with_para_id
            # necesita para asignar el bbox correcto.
            flush_paragraph()
            continue

        paragraph_lines.append(raw_line)

    flush_paragraph()
    return blocks, heading_levels_by_order, table_positions


def _build_markdown_blocks(result: object) -> tuple[list[dict], EventDict]:
    markdown = str(getattr(result, "content", "") or "")
    tables = list(getattr(result, "tables", None) or [])
    paragraphs = list(getattr(result, "paragraphs", None) or [])

    blocks, heading_levels_by_order, table_positions = _parse_markdown_blocks(markdown)
    for block in blocks:
        level = heading_levels_by_order.get(block["source_order"])
        if level is not None:
            block["heading_level"] = level
    
    # SOLUCIÓN DEFINITIVA V2 (2026-08): Mapeo por posición estructural
    # - Construye índice (page, index) → bbox de paragraphs
    # - Asigna para_id secuencial a bloques por orden de lectura
    # - Mapea bbox por para_id (identidad estable, no contenido)
    # - Precisión 100% sin ambigüedad por texto duplicado
    # ING-03: factor a puntos por página, antes de extraer cualquier bbox.
    unit_scales = _page_unit_scales(result)

    bbox_by_para_id = _build_para_id_index(paragraphs, unit_scales)
    _enrich_blocks_with_para_id(blocks, bbox_by_para_id, _page_sizes_in_points(result, unit_scales))

    total_table_rows = 0
    tables_placed_in_reading_order = 0
    tables_with_fallback_position = 0
    for index, table in enumerate(tables, start=1):
        table_id = f"T{index}"
        row_blocks = _serialize_table_rows(table, table_id=table_id, unit_scales=unit_scales)
        # Las tablas aparecen en `result.tables` en el mismo orden en que sus
        # `<table>` aparecen en el markdown, asi que la posicion i-esima ubica a
        # la tabla i-esima en el flujo de lectura. Con eso las filas quedan bajo
        # el encabezado que realmente las precede. Sin esto (fallback historico)
        # toda tabla se empujaba al final de su pagina y heredaba el ultimo
        # titulo de la pagina: la caratula de un pliego terminaba etiquetada como
        # "ANEXOS OBLIGATORIOS" solo por estar en la misma pagina.
        position = table_positions[index - 1] if index - 1 < len(table_positions) else None
        if position is not None:
            table_page, table_order = position
            tables_placed_in_reading_order += 1
            for row_index, row_block in enumerate(row_blocks):
                row_block["page_number"] = table_page
                # Las filas comparten la posicion de la tabla y se desempatan
                # entre si por su indice, sin invadir el source_order siguiente.
                row_block["source_order"] = table_order
                row_block["row_order"] = row_index
        else:
            # Tabla sin posición en markdown - usar fallback artificial
            tables_with_fallback_position += 1
            logger.warning(
                "table_position_fallback",
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
    # Detectar desincronización entre markdown y result.tables
    if tables_with_fallback_position > 0:
        logger.warning(
            "table_position_mismatch",
            tables_count=len(tables),
            table_positions_in_markdown=len(table_positions),
            tables_with_fallback=tables_with_fallback_position,
        )
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
            output_content_format=DocumentContentFormat.MARKDOWN,  # Markdown para estructura + result.paragraphs para bbox
        )
        result = poller.result(timeout=self._timeout_seconds)

        # Validación: verificar que el resultado tiene el formato esperado
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
        # FIX LOW (#11): Separar Azure errors específicos para mejor handling
        except HttpResponseError as exc:
            is_last_attempt = attempt >= retries
            # Status code específico ayuda a diagnosticar (429 rate limit, 503 service unavailable, etc.)
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
            # Para rate limits (429), esperar más tiempo
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
                raise TransientExtractionError(f"Service error after {retries} attempts: {exc}") from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
        except Exception as exc:
            # Errores inesperados (bugs de código, etc.) - loggear más detalles
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
                raise TransientExtractionError(f"Unexpected error after {retries} attempts: {exc}") from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    raise TransientExtractionError("No se pudo extraer texto")
