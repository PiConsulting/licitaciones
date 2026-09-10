"""Union de bloques intermedios (encabezados normalizados + tablas) en la secuencia final antes de chunkear."""
from __future__ import annotations


import structlog

from indexing.chunking.page_furniture import (
    _drop_index_listings,
    _drop_repeated_page_furniture,
)
from indexing.chunking.headings import (
    _detect_repeated_heading_boilerplate,
    _is_bullet_marker_heading,
    _merge_split_headings_across_pages,
    _merge_truncated_headings_with_body,
    _nest_unnumbered_headings_under_numbered,
    _normalize_decimal_heading_levels,
    _normalize_heading_value,
    _normalize_numbered_heading_levels,
    _promote_run_in_headings,
    _strip_boilerplate_fragments,
)

logger = structlog.get_logger(__name__)

_TABLE_CONTEXT_MAX_CHARS = 300


def _table_group_key(block: dict) -> object | None:
    """Clave para agrupar las filas de una misma tabla, sea cual sea la forma
    de `table_ref`.
    """
    table_ref = block.get("table_ref")
    if isinstance(table_ref, dict):
        return table_ref.get("table_id")
    if isinstance(table_ref, str) and table_ref:
        return table_ref
    return None


def _to_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Recorre los bloques de Document Intelligence (encabezado si trae
    `heading_level`, parrafo o fila de tabla si no) en orden de lectura y les
    asigna `heading_path`: la lista de encabezados ancestros vigentes en ese
    punto del documento, usando directamente el nivel que ya resolvio Azure
    (cantidad de `#` en el markdown) -- sin adivinar profundidad por regex."""
    ordered = sorted(
        blocks,
        key=lambda item: (
            int(item["page_number"]),
            int(item.get("source_order", 0)),
            int(item.get("row_order", 0)),
        ),
    )

    ordered = _drop_index_listings(ordered)

    ordered = _drop_repeated_page_furniture(ordered)

    ordered = _merge_split_headings_across_pages(ordered)

    ordered = _merge_truncated_headings_with_body(ordered)

    ordered = _normalize_numbered_heading_levels(ordered)

    ordered = _normalize_decimal_heading_levels(ordered)
    ordered = _promote_run_in_headings(ordered)

    ordered = _nest_unnumbered_headings_under_numbered(ordered)
    boilerplate = _detect_repeated_heading_boilerplate(ordered)

    heading_stack: list[tuple[str, int]] = []
    heading_has_body: list[bool] = []
    intermediate: list[dict] = []
    last_page = 1

    def current_path() -> list[str]:
        return [text for text, _level in heading_stack]

    def pop_to_level(level: int, page_number: int) -> None:
        while heading_stack and heading_stack[-1][1] >= level:
            text, _popped_level = heading_stack.pop()
            had_body = heading_has_body.pop()
            if not had_body:
                intermediate.append(
                    {
                        "page_number": page_number,
                        "block_type": "paragraph",
                        "content": "",
                        "table_ref": None,
                        "heading_path": current_path() + [text],
                        "is_heading": True,
                    }
                )

    for block in ordered:
        content = str(block.get("content", "")).strip()
        if not content:
            continue
        last_page = int(block["page_number"])
        level = block.get("heading_level")

        if level is not None:
            normalized = _normalize_heading_value(content)
            if normalized.lower() in boilerplate:
                continue
            normalized = _strip_boilerplate_fragments(normalized, boilerplate)
            if not normalized:
                continue

            if _is_bullet_marker_heading(normalized):
                # DI marco una vineta / "ITEM N" / "col_x" como encabezado: no es
                # un titulo de seccion. No se apila (contaminaria el heading_path
                # de todo lo que cuelga debajo); cae al bloque de cuerpo de abajo.
                logger.debug(
                    "heading_demoted_bullet_marker", page=last_page, text=normalized[:80]
                )
                block = {**block, "heading_level": None, "block_type": "paragraph"}
            else:
                logger.debug(
                    "heading_detected",
                    page=last_page,
                    level=level,
                    text=normalized[:80],
                    current_stack=[h for h, _ in heading_stack],
                )

                pop_to_level(int(level), last_page)
                heading_stack.append((normalized, int(level)))
                heading_has_body.append(False)
                continue

        if heading_has_body:
            for index in range(len(heading_has_body)):
                heading_has_body[index] = True

        intermediate.append(
            {
                "page_number": last_page,
                "block_type": block.get("block_type", "paragraph"),
                "content": content,
                "table_ref": block.get("table_ref"),
                "heading_path": current_path(),
                "is_heading": False,
                "para_id": block.get("para_id"),  # DEFINITIVO V2: Propagar para_id
                "bbox": block.get("bbox", []),
                **({"lines": block["lines"]} if block.get("lines") else {}),
            }
        )

    pop_to_level(0, last_page)
    return intermediate


def _preceding_table_context(merged: list[dict], table_block: dict) -> str | None:
    """Determina el texto que introduce a una tabla (el parrafo justo antes,
    ej. "La evaluacion se realizara segun la siguiente tabla:") para que nunca
    quede separado de las filas que explica. Las filas siguientes de la misma
    tabla heredan el mismo contexto que la primera."""
    if not merged:
        return None

    previous = merged[-1]

    if previous.get("block_type") == "table":
        previous_ref = previous.get("table_ref") or {}
        current_ref = table_block.get("table_ref") or {}
        if previous_ref.get("table_id") is not None and previous_ref.get(
            "table_id"
        ) == current_ref.get("table_id"):
            return previous.get("table_context")
        return None

    if previous.get("is_heading") or previous["page_number"] != table_block["page_number"]:
        return None

    prev_path = previous.get("heading_path") or []
    table_path = table_block.get("heading_path") or []
    same_path = prev_path == table_path
    is_ancestor = len(prev_path) < len(table_path) and table_path[: len(prev_path)] == prev_path
    if same_path or is_ancestor:
        return _introductory_tail(previous["content"])
    return None


def _introductory_tail(content: object) -> str | None:
    """La frase que introduce a la tabla: el ÚLTIMO párrafo del bloque previo."""
    texto = str(content or "").strip()
    if not texto:
        return None

    parrafos = [parte.strip() for parte in texto.split("\n\n") if parte.strip()]
    if not parrafos:
        return None

    cola = parrafos[-1]
    if len(cola) <= _TABLE_CONTEXT_MAX_CHARS:
        return cola

    recorte = cola[-_TABLE_CONTEXT_MAX_CHARS:]
    for separador in (". ", "; ", ": "):
        posicion = recorte.find(separador)
        if 0 <= posicion < len(recorte) // 2:
            return recorte[posicion + len(separador) :].strip()
    espacio = recorte.find(" ")
    return recorte[espacio + 1 :].strip() if espacio >= 0 else recorte.strip()


def _merge_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Junta bloques consecutivos que comparten el mismo heading_path en un
    solo bloque semántico para RAG.
    """
    from infra.config import get_settings

    settings = get_settings()
    max_table_tokens = settings.chunking_max_table_tokens

    merged: list[dict] = []

    for raw_block in blocks:
        block = dict(raw_block)

        if block.get("block_type") == "table":
            context = _preceding_table_context(merged, block)
            if context:
                block["table_context"] = context
            if merged:
                previous = merged[-1]
                previous_ref = previous.get("table_ref") or {}
                current_ref = block.get("table_ref") or {}
                same_table = (
                    previous.get("block_type") == "table"
                    and previous_ref.get("table_id") is not None
                    and previous_ref.get("table_id") == current_ref.get("table_id")
                )

                if same_table:
                    if "merged_blocks" not in previous:
                        original_content = previous["content"]
                        previous["merged_blocks"] = [
                            {
                                "para_id": previous.get("para_id"),
                                "bbox": previous.get("bbox", []),
                                **({"lines": previous["lines"]} if previous.get("lines") else {}),
                                "content": original_content,
                            }
                        ]
                    combined_content = f"{previous['content']}\n{block['content']}"
                    approx_tokens = len(combined_content) / 4

                    if approx_tokens > max_table_tokens:
                        block["table_context"] = previous.get("table_context", "")
                        block["merged_blocks"] = [
                            {
                                "para_id": block.get("para_id"),
                                "bbox": block.get("bbox", []),
                                **({"lines": block["lines"]} if block.get("lines") else {}),
                                "content": block.get("content", ""),
                            }
                        ]
                        merged.append(block)
                        continue
                    previous["merged_blocks"].append(
                        {
                            "para_id": block.get("para_id"),
                            "bbox": block.get("bbox", []),
                            **({"lines": block["lines"]} if block.get("lines") else {}),
                            "content": block.get("content", ""),
                        }
                    )

                    previous["content"] = combined_content

                    if "table_ref" in previous and "row_index" in current_ref:
                        previous["table_ref"]["row_index"] = current_ref["row_index"]

                    continue  # No agregar block actual, ya está mergeado

            if "merged_blocks" not in block:
                block["merged_blocks"] = [
                    {
                        "para_id": block.get("para_id"),
                        "bbox": block.get("bbox", []),
                        **({"lines": block["lines"]} if block.get("lines") else {}),
                        "content": block.get("content", ""),
                    }
                ]
            merged.append(block)
            continue

        if block.get("is_heading"):
            if "merged_blocks" not in block:
                block["merged_blocks"] = []
            merged.append(block)
            continue

        if merged:
            previous = merged[-1]
            can_merge = (
                previous.get("block_type") != "table"
                and not previous.get("is_heading")
                and previous["page_number"] == block["page_number"]
                and previous.get("heading_path") == block.get("heading_path")
            )
            if can_merge:
                if "merged_blocks" not in previous:
                    original_content = previous["content"]
                    previous["merged_blocks"] = [
                        {
                            "para_id": previous.get("para_id"),
                            "bbox": previous.get("bbox", []),
                            **({"lines": previous["lines"]} if previous.get("lines") else {}),
                            "content": original_content,
                        }
                    ]
                previous["merged_blocks"].append(
                    {
                        "para_id": block.get("para_id"),
                        "bbox": block.get("bbox", []),
                        **({"lines": block["lines"]} if block.get("lines") else {}),
                        "content": block.get("content", ""),
                    }
                )
                previous["content"] = f"{previous['content']}\n\n{block['content']}"
                continue
        if "merged_blocks" not in block:
            block["merged_blocks"] = [
                {
                    "para_id": block.get("para_id"),
                    "bbox": block.get("bbox", []),
                    **({"lines": block["lines"]} if block.get("lines") else {}),
                    "content": block.get("content", ""),
                }
            ]
        merged.append(block)

    return merged
