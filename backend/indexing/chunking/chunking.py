"""Entrypoint de chunking: arma los bloques intermedios y las categorias, y produce los chunks finales (padre/hijo) que se indexan."""
from __future__ import annotations

from uuid import UUID

import structlog

from indexing.chunking.block_merging import _merge_intermediate_blocks, _to_intermediate_blocks
from indexing.chunking.classification import _normalize_for_matching, classify_chunk_categories
from indexing.chunking.headings import _detect_incisos
from indexing.chunking.text_splitting import _split_block_into_chunks, _tokenize

logger = structlog.get_logger(__name__)

_PARENT_CHILD_MIN_CHARS = 800
_PROGRAMMING_ERRORS = (NameError, AttributeError, TypeError)


def _blocks_data_for(block: dict, texto: str, page_number: int) -> list[dict]:
    """Los bloques originales que efectivamente están en `texto`."""
    merged_blocks = block.get("merged_blocks") or []
    if not merged_blocks:
        return [
            {
                "para_id": block.get("para_id"),
                "page": page_number,
                "bbox": block.get("bbox", []),
                **({"lines": block["lines"]} if block.get("lines") else {}),
                "content": block.get("content", ""),
            }
        ]

    texto_normalizado = _normalize_for_matching(texto)
    incluidos = [
        mb
        for mb in merged_blocks
        if (contenido := _normalize_for_matching(str(mb.get("content", ""))))
        and contenido in texto_normalizado
    ]

    if not incluidos:
        incluidos = merged_blocks

    return [
        {
            "para_id": mb.get("para_id"),
            "page": page_number,
            "bbox": mb.get("bbox", []),
            **({"lines": mb["lines"]} if mb.get("lines") else {}),
            "content": mb.get("content", ""),
        }
        for mb in incluidos
    ]


def create_chunks(
    blocks: list[dict],
    document_id: str | UUID,
    correlation_id: str | UUID,
    *,
    chunk_size: int = 700,
    overlap: int = 120,
) -> list[dict]:
    """Arma los chunks finales a partir de los bloques que devuelve
    `indexing.document_intelligence.extract_text()` (encabezado/parrafo/fila
    de tabla con pagina y, si es encabezado, su nivel ya resuelto por Azure).
    Cada chunk final es siempre "heading_path completo + su contenido" -- nunca
    un titulo suelto ni un parrafo sin contexto de que seccion es."""
    logger.info(
        "chunking_started",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        blocks=len(blocks),
        chunk_size=chunk_size,
        overlap=overlap,
    )

    intermediate = _to_intermediate_blocks(blocks)
    intermediate = _merge_intermediate_blocks(intermediate)

    chunks: list[dict] = []
    chunk_index = 0
    saltados: list[dict] = []

    for block in intermediate:
        try:
            page_number = int(block["page_number"])
            block_type = str(block.get("block_type", "paragraph"))
            heading_path = list(block.get("heading_path") or [])

            section_path = " > ".join(heading_path) if heading_path else "general"
            title = heading_path[-1] if heading_path else None  # Último nivel = título de sección

            if block_type == "table":
                row_content = str(block["content"])
                context_parts = [block.get("table_context"), row_content]
                full_content = "\n\n".join([p for p in context_parts if p])
                row_tokens = _tokenize(full_content)
                if not row_tokens:
                    continue

                blocks_data = _blocks_data_for(block, full_content, page_number)

                source = {
                    "page": page_number,
                    "block_type": "table",
                    "blocks": blocks_data,
                }

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": full_content,  # SOLO table_context + rows (sin heading)
                    "token_count": len(row_tokens),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "title": title,  # RAG: Campo explícito para embedding
                    "block_type": "table",
                    "table_ref": block.get("table_ref"),
                    "source": source,  # RAG PHASE 3: Metadata estructurada para highlighting
                    "blocks": blocks_data,  # LEGACY: Mantener por compatibilidad
                    "chunk_type": "normal",
                }
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
                continue

            if block.get("is_heading"):
                heading_text = heading_path[-1] if heading_path else ""
                content_pieces = [heading_text] if heading_text else []
            else:
                body = str(block["content"]).strip()
                content_pieces = _split_block_into_chunks(body, chunk_size, overlap) if body else []

            for chunk_content in content_pieces:
                if not chunk_content.strip():
                    continue

                blocks_data = _blocks_data_for(block, chunk_content, page_number)

                source = {
                    "page": page_number,
                    "block_type": "paragraph",
                    "blocks": blocks_data,
                }

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": chunk_content,  # SOLO el párrafo puro (sin heading)
                    "token_count": len(_tokenize(chunk_content)),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "title": title,  # RAG: Campo explícito para embedding
                    "block_type": "paragraph",
                    "table_ref": None,
                    "source": source,  # RAG PHASE 3: Metadata estructurada para highlighting
                    "blocks": blocks_data,  # LEGACY: Mantener por compatibilidad
                    "chunk_type": "normal",
                }

                incisos = (
                    _detect_incisos(chunk_content)
                    if len(chunk_content) >= _PARENT_CHILD_MIN_CHARS
                    else []
                )

                if incisos:
                    parent_index = chunk_index
                    chunk_dict["chunk_type"] = "parent"

                    classification = classify_chunk_categories(chunk_dict)
                    chunk_dict["primary_category"] = classification["primary_category"]
                    chunk_dict["secondary_categories"] = classification["secondary_categories"]

                    child_indices: list[int] = []
                    child_chunk_dicts: list[dict] = []
                    for inciso in incisos:
                        chunk_index += 1
                        inciso_label = inciso["label"].rstrip(").")
                        child_content = inciso["text"]

                        child_source = {
                            "page": page_number,
                            "block_type": "paragraph",
                            "blocks": _blocks_data_for(block, child_content, page_number),
                        }
                        child_dict = {
                            **chunk_dict,
                            "chunk_index": chunk_index,
                            "content": child_content,
                            "token_count": len(_tokenize(child_content)),
                            "title": f"{title}.{inciso_label}" if title else inciso_label,
                            "section_path": f"{section_path} > {inciso['label']}",
                            "chunk_type": "child",
                            "parent_chunk_index": parent_index,
                            "source": child_source,
                            "blocks": list(child_source["blocks"]),
                        }
                        child_dict.pop("child_chunk_indices", None)

                        child_classification = classify_chunk_categories(child_dict)
                        child_dict["primary_category"] = child_classification["primary_category"]
                        child_dict["secondary_categories"] = child_classification[
                            "secondary_categories"
                        ]
                        child_chunk_dicts.append(child_dict)
                        child_indices.append(chunk_index)

                    chunk_dict["child_chunk_indices"] = child_indices
                    chunks.append(chunk_dict)
                    chunks.extend(child_chunk_dicts)
                    chunk_index += 1
                    continue
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
        except _PROGRAMMING_ERRORS:
            raise
        except Exception as exc:  # noqa: BLE001
            saltados.append(
                {
                    "page_number": block.get("page_number"),
                    "heading_path": block.get("heading_path"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            logger.warning(
                "chunking_block_skipped",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                heading_path=block.get("heading_path"),
                page_number=block.get("page_number"),
                error=str(exc),
            )
            continue

    if saltados:
        logger.error(
            "chunking_blocks_skipped_total",
            correlation_id=str(correlation_id),
            document_id=str(document_id),
            bloques_saltados=len(saltados),
            bloques_totales=len(intermediate),
            paginas=sorted({s["page_number"] for s in saltados if s["page_number"] is not None}),
            errores=sorted({s["error"] for s in saltados})[:5],
            impact="el documento quedó indexado sin esos bloques",
        )

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
        bloques_saltados=len(saltados),
    )
    return chunks
