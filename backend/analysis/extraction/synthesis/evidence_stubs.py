"""Resolucion de cada `evidence` que devuelve el LLM de sintesis a un stub de cita YA VERIFICADA de un item."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.schemas import CategoryNarrative, RawCategoryNarrative
from analysis.extraction.synthesis.text_matching import (
    _normalize_text_for_comparison,
    _overlap_ratio,
)

logger = structlog.get_logger(__name__)


def _stub_for_evidence(
    evidence: Any,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> tuple[dict[str, Any], str] | None:
    """Ancla una evidencia del LLM a una cita YA VERIFICADA del item que ella
    misma dice respaldar. Devuelve `(stub, citation)` o None.
    """
    # Import diferido: source_resolution importa de este módulo a nivel de
    # módulo (_resolve_from_evidence); importar acá arriba crearía un ciclo.
    from analysis.extraction.synthesis.source_resolution import _item_source_stubs

    candidate_stubs: list[dict[str, Any]] = []
    for ref in evidence.item_refs:
        if 0 <= ref < len(items):
            candidate_stubs.extend(_item_source_stubs(items[ref]))

    if not candidate_stubs:
        logger.warning(
            "evidence_sin_item_verificable",
            correlation_id=correlation_id,
            item_refs=list(evidence.item_refs),
            item_count=len(items),
            text_preview=evidence.text[:80],
            reason=(
                "la evidencia no referencia ningún item con citas verificadas: "
                "no hay contra qué anclarla"
            ),
        )
        return None

    evidence_normalized = _normalize_text_for_comparison(evidence.text)

    if evidence_normalized:
        for stub in candidate_stubs:
            if evidence_normalized in _normalize_text_for_comparison(stub["citation"]):
                return stub, evidence.text.strip()

    best = max(candidate_stubs, key=lambda stub: _overlap_ratio(evidence.text, stub["citation"]))
    logger.warning(
        "evidence_text_no_es_fragmento_de_cita_verificada",
        correlation_id=correlation_id,
        item_refs=list(evidence.item_refs),
        text_preview=evidence.text[:100],
        citation_preview=best["citation"][:100],
        overlap=round(_overlap_ratio(evidence.text, best["citation"]), 2),
        impact="se pierde precisión de resaltado, no la afirmación ni la trazabilidad",
    )
    return best, best["citation"]


def _chunk_id_for_stub(stub: dict[str, Any], chunks_by_id: dict[str, dict] | None) -> str | None:
    """El `chunk_id` que dejó anotado la etapa de extracción (ATR-01). Para
    items de análisis viejos que no lo tengan, se busca el chunk de esa página
    que contenga la cita."""
    chunk_id = stub.get("chunk_id")
    if chunk_id:
        return str(chunk_id)

    if not chunks_by_id:
        return None

    citation_normalized = _normalize_text_for_comparison(stub["citation"])
    if not citation_normalized:
        return None

    for candidate in chunks_by_id.values():
        if candidate.get("document_id") != stub["document_id"]:
            continue
        if candidate.get("page_number") != stub["page_number"]:
            continue
        if citation_normalized in _normalize_text_for_comparison(candidate.get("content", "")):
            resolved = candidate.get("chunk_id") or candidate.get("id")
            return str(resolved) if resolved else None

    return None


def _resolve_from_evidence(
    raw: RawCategoryNarrative,
    chunks_by_id: dict[str, dict] | None,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> CategoryNarrative:
    """Construye `CategoryNarrative` desde las evidencias del LLM, ancladas a
    las citas verificadas de los items que cada evidencia referencia.

    Ver `_stub_for_evidence` para el porqué del anclaje (SYN-01 / SYN-04).
    """
    all_sources: list[dict[str, Any]] = []
    source_id_by_key: dict[tuple[str, int, str], int] = {}

    resolved_evidence: list[tuple[set[int], int]] = []

    for evidence in raw.evidence:
        anchored = _stub_for_evidence(evidence, items, correlation_id=correlation_id)
        if anchored is None:
            continue
        stub, citation = anchored

        key = (
            stub["document_id"],
            stub["page_number"],
            _normalize_text_for_comparison(citation),
        )
        source_id = source_id_by_key.get(key)
        if source_id is None:
            source: dict[str, Any] = {
                "id": len(all_sources),
                "document_id": stub["document_id"],
                "page_number": stub["page_number"],
                "citation": citation,
                "unverified": False,
                "highlight_regions": [],
            }
            chunk_id = _chunk_id_for_stub(stub, chunks_by_id)
            if chunk_id:
                source["chunk_id"] = chunk_id
            if stub.get("block_id"):
                source["block_id"] = stub["block_id"]

            source_id = source["id"]
            all_sources.append(source)
            source_id_by_key[key] = source_id

        resolved_evidence.append((set(evidence.item_refs), source_id))

    def get_source_ids_for_item_refs(item_refs: list[int]) -> list[int]:
        wanted = set(item_refs)
        source_ids: list[int] = []
        for evidence_refs, source_id in resolved_evidence:
            if evidence_refs & wanted and source_id not in source_ids:
                source_ids.append(source_id)
        return source_ids

    blocks_data: list[dict[str, Any]] = []
    for block in raw.blocks:
        if block.type == "paragraph":
            source_ids = get_source_ids_for_item_refs(block.item_refs)
            if not source_ids:
                logger.info(
                    "paragraph_dropped_no_evidence",
                    correlation_id=correlation_id,
                    text=block.text[:100],
                )
                continue
            blocks_data.append(
                {
                    "type": "paragraph",
                    "text": block.text,
                    "confidence_level": block.confidence_level,
                    "source_ids": source_ids,
                }
            )
        elif block.type == "bullet_list":
            kept_items = []
            for bullet in block.items:
                source_ids = get_source_ids_for_item_refs(bullet.item_refs)
                if not source_ids:
                    continue
                kept_items.append(
                    {
                        "text": bullet.text,
                        "resumen": bullet.resumen,
                        "confidence_level": bullet.confidence_level,
                        "source_ids": source_ids,
                    }
                )
            if kept_items:
                blocks_data.append({"type": "bullet_list", "items": kept_items})
        elif block.type == "table":
            kept_rows = []
            for row in block.rows:
                source_ids = get_source_ids_for_item_refs(row.item_refs)
                if not source_ids:
                    continue
                kept_rows.append(
                    {
                        "cells": row.cells,
                        "confidence_level": row.confidence_level,
                        "source_ids": source_ids,
                    }
                )
            if kept_rows:
                blocks_data.append({"type": "table", "headers": block.headers, "rows": kept_rows})

    logger.info(
        "narrative_resolved_from_evidence",
        correlation_id=correlation_id,
        evidence_count=len(raw.evidence),
        evidence_anchored=len(resolved_evidence),
        sources_created=len(all_sources),
        blocks_retained=len(blocks_data),
    )

    return CategoryNarrative.model_validate({"blocks": blocks_data, "sources": all_sources})
