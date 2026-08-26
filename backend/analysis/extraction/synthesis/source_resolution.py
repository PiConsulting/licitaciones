"""Resolucion de las fuentes de una narrativa completa a partir de las evidencias del LLM, con dedupe determinista."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.schemas import CategoryNarrative, CITATION_MIN_CHARS, RawCategoryNarrative
from analysis.extraction.synthesis.evidence_stubs import _resolve_from_evidence
from analysis.extraction.synthesis.narrative_counting import (
    _count_narrative_elements,
    _count_raw_narrative_elements,
)
from analysis.extraction.synthesis.text_matching import _normalize_text_for_comparison

logger = structlog.get_logger(__name__)


def _dedupe_narrative_sources(
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """Deduplica sources en narrative usando normalización de texto.

    Cuando la source trae `block_id` (mismo párrafo/bloque de origen), se
    agrupan por `(document_id, page_number, block_id)`: las citations de
    ese mismo párrafo se combinan en una sola, separadas por "[...]", en
    vez de quedar como sources repetidas. Sin `block_id` se conserva el
    comportamiento legacy: dedupe por texto normalizado de la citation,
    sin combinar.
    """
    seen: dict[tuple[str, int, str], int] = {}
    deduped: list[dict[str, Any]] = []
    id_mapping: dict[int, int] = {}

    for source in sources:
        doc_id = str(source.get("document_id", ""))
        page = int(source.get("page_number", 0) or 0)
        citation = str(source.get("citation", ""))
        block_id = str(source.get("block_id")) if source.get("block_id") else None

        if block_id:
            key = (doc_id, page, f"block::{block_id}")
        else:
            normalized_citation = _normalize_text_for_comparison(citation)
            key = (doc_id, page, normalized_citation)

        original_id = int(source.get("id", 0))

        if key in seen:
            canonical_id = seen[key]
            id_mapping[original_id] = canonical_id

            if block_id:
                canonical_source = deduped[canonical_id]
                existing_citation = canonical_source.get("citation", "")
                if citation and citation not in existing_citation:
                    canonical_source["citation"] = (
                        f"{existing_citation} [...] {citation}"
                        if existing_citation
                        else citation
                    )
                if source.get("unverified"):
                    canonical_source["unverified"] = True
        else:
            new_id = len(deduped)
            seen[key] = new_id
            id_mapping[original_id] = new_id
            deduped_source: dict[str, Any] = {
                "id": new_id,
                "document_id": doc_id,
                "page_number": page,
                "citation": citation,
            }

            if block_id:
                deduped_source["block_id"] = block_id

            if source.get("chunk_id"):
                deduped_source["chunk_id"] = str(source.get("chunk_id"))

            if source.get("unverified"):
                deduped_source["unverified"] = True
            deduped.append(deduped_source)

    return deduped, id_mapping


def _item_source_stubs(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Los `source_references` propios de UN item, normalizados a la forma
    minima que necesita el pool de sources. Nunca texto inventado: siempre una
    copia de lo que el item ya trae verificado desde la extraccion -- esta es
    la unica fuente de verdad para lo que puede llegar a `sources`."""
    stubs: list[dict[str, Any]] = []
    for ref in item.get("source_references") or []:
        citation = str(ref.get("citation", "")).strip()
        if len(citation) < CITATION_MIN_CHARS:
            continue
        stub = {
            "document_id": str(ref.get("document_id", "")),
            "page_number": int(ref.get("page_number", 0) or 0),
            "citation": citation,
        }

        block_id = ref.get("block_id")
        if block_id:
            stub["block_id"] = str(block_id)

        chunk_id = ref.get("chunk_id")
        if chunk_id:
            stub["chunk_id"] = str(chunk_id)
        stubs.append(stub)
    return stubs


def _resolve_narrative_sources(
    raw: RawCategoryNarrative,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
    chunks_by_id: dict[str, dict] | None = None,
) -> CategoryNarrative:
    """Traduce la salida cruda del LLM (bloques con `item_refs`) a un
    `CategoryNarrative` (bloques con `source_ids` + `sources`), resolviendo
    cada referencia contra los `source_references` PROPIOS del item apuntado.
    """

    total_elements = _count_raw_narrative_elements(raw)

    if raw.evidence:
        logger.info(
            "using_evidence_based_resolution",
            correlation_id=correlation_id,
            evidence_count=len(raw.evidence),
        )
        evidence_narrative = _resolve_from_evidence(
            raw, chunks_by_id, items, correlation_id=correlation_id
        )
        resolved_elements = _count_narrative_elements(evidence_narrative)

        if resolved_elements >= total_elements and resolved_elements > 0:
            return evidence_narrative

        logger.error(
            "evidence_resolution_incomplete_falling_back",
            correlation_id=correlation_id,
            evidence_count=len(raw.evidence),
            elements_expected=total_elements,
            elements_resolved=resolved_elements,
            elements_lost=total_elements - resolved_elements,
            indexed_chunks=len(chunks_by_id) if chunks_by_id else 0,
            reason=(
                "la resolución por evidencias no pudo respaldar todas las afirmaciones: "
                "hay evidencias que no referencian ningún item con citas verificadas, "
                "o bloques cuyos item_refs no coinciden con los de ninguna evidencia; "
                "se usa item_refs, que resuelve contra las citas ya verificadas"
            ),
        )

    logger.info(
        "using_item_refs_resolution",
        correlation_id=correlation_id,
        has_evidence=bool(raw.evidence),
        evidence_count=len(raw.evidence) if raw.evidence else 0,
        has_chunks_by_id=chunks_by_id is not None,
    )
    item_stubs = [_item_source_stubs(item) for item in items]
    all_stubs: list[dict[str, Any]] = []

    def resolve(item_refs: list[int], *, context: str) -> list[int] | None:
        valid_indexes = [i for i in item_refs if 0 <= i < len(items)]
        invalid_indexes = [i for i in item_refs if i not in valid_indexes]
        if invalid_indexes:
            logger.warning(
                "narrative_item_ref_out_of_range",
                correlation_id=correlation_id,
                context=context,
                invalid_refs=invalid_indexes,
                item_count=len(items),
            )

        temp_ids: list[int] = []
        seen: set[tuple[str, int, str]] = set()
        for index in valid_indexes:
            for stub in item_stubs[index]:
                key = (
                    stub["document_id"],
                    stub["page_number"],
                    _normalize_text_for_comparison(stub["citation"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                stub_with_id = {**stub, "id": len(all_stubs)}
                all_stubs.append(stub_with_id)
                temp_ids.append(stub_with_id["id"])

        if not temp_ids:
            logger.info(
                "narrative_element_dropped_no_evidence",
                correlation_id=correlation_id,
                context=context,
            )
            return None
        return temp_ids

    retained_blocks: list[dict[str, Any]] = []
    for block in raw.blocks:
        if block.type == "paragraph":
            source_ids = resolve(block.item_refs, context="paragraph")
            if source_ids is None:
                continue
            retained_blocks.append(
                {
                    "type": "paragraph",
                    "text": block.text,
                    "confidence_level": block.confidence_level,
                    "source_ids": source_ids,
                }
            )
        elif block.type == "bullet_list":
            kept_items: list[dict[str, Any]] = []
            for bullet in block.items:
                source_ids = resolve(bullet.item_refs, context="bullet_item")
                if source_ids is None:
                    continue
                kept_items.append(
                    {
                        "text": bullet.text,
                        "confidence_level": bullet.confidence_level,
                        "source_ids": source_ids,
                    }
                )
            if kept_items:
                retained_blocks.append({"type": "bullet_list", "items": kept_items})
        elif block.type == "table":
            kept_rows: list[dict[str, Any]] = []
            for row in block.rows:
                source_ids = resolve(row.item_refs, context="table_row")
                if source_ids is None:
                    continue
                kept_rows.append(
                    {
                        "cells": row.cells,
                        "confidence_level": row.confidence_level,
                        "source_ids": source_ids,
                    }
                )
            if kept_rows:
                retained_blocks.append(
                    {"type": "table", "headers": block.headers, "rows": kept_rows}
                )

    deduped_sources, id_mapping = _dedupe_narrative_sources(all_stubs)

    def remap(block_data: dict[str, Any]) -> dict[str, Any]:
        if isinstance(block_data.get("source_ids"), list):
            block_data["source_ids"] = [
                id_mapping.get(sid, sid) for sid in block_data["source_ids"]
            ]
        for key in ("items", "rows"):
            nested = block_data.get(key)
            if isinstance(nested, list):
                block_data[key] = [remap(entry) for entry in nested]
        return block_data

    blocks_data = [remap(block) for block in retained_blocks]

    if len(all_stubs) > len(deduped_sources):
        logger.info(
            "narrative_sources_deduplicated",
            correlation_id=correlation_id,
            original=len(all_stubs),
            deduplicated=len(deduped_sources),
            removed=len(all_stubs) - len(deduped_sources),
        )

    resolved = CategoryNarrative.model_validate({"blocks": blocks_data, "sources": deduped_sources})

    resolved_elements = _count_narrative_elements(resolved)
    if resolved_elements < total_elements:
        logger.warning(
            "narrative_elements_dropped_no_evidence",
            correlation_id=correlation_id,
            elements_expected=total_elements,
            elements_resolved=resolved_elements,
            elements_lost=total_elements - resolved_elements,
            items_available=len(items),
            items_with_usable_citations=sum(1 for stubs in item_stubs if stubs),
        )

    return resolved
