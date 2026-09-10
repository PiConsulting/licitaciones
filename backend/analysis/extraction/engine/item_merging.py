"""Fusión de items duplicados o partidos entre sí, por identidad débil o por sección del documento."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import structlog

from analysis.extraction.engine.citation_grounding import (
    _grounding_chunk_ids_for_item,
    _normalize_for_grounding,
)

logger = structlog.get_logger(__name__)

_GENERIC_FALLBACK_TIPOS = {"otro", "otra", "no encontrado"}
_MERGEABLE_TEXT_FIELDS = ("texto_original", "expresion_relativa", "valor")
_STATUS_RANK = {"success": 3, "partial": 2, "not_applicable": 1, "not_found": 0, "failed": 0}


def _has_weak_identity(item: dict[str, Any]) -> bool:
    """Un ítem con `tipo` genérico, o con status parcial y confianza baja, no
    tiene entidad propia clara: es un candidato natural a ser en realidad un
    pedazo de OTRO ítem (ver `_merge_split_fact_items`)."""
    tipo = str(item.get("tipo") or "").strip().lower()
    if tipo in _GENERIC_FALLBACK_TIPOS:
        return True
    status = str(item.get("extraction_status") or "")
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    return status == "partial" and confidence < 0.65


def _merge_two_items(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)

    for field_name in _MERGEABLE_TEXT_FIELDS:
        primary_text = str(merged.get(field_name) or "").strip()
        secondary_text = str(secondary.get(field_name) or "").strip()
        if not secondary_text:
            continue
        if primary_text and secondary_text.lower() in primary_text.lower():
            continue
        merged[field_name] = (
            f"{primary_text} {secondary_text}".strip() if primary_text else secondary_text
        )

    existing_citations = {
        _normalize_for_grounding(ref.get("citation"))
        for ref in merged.get("source_references") or []
        if isinstance(ref, dict)
    }
    combined_refs = list(merged.get("source_references") or [])
    for ref in secondary.get("source_references") or []:
        if not isinstance(ref, dict):
            continue
        normalized_citation = _normalize_for_grounding(ref.get("citation"))
        if normalized_citation and normalized_citation not in existing_citations:
            combined_refs.append(ref)
            existing_citations.add(normalized_citation)
    merged["source_references"] = combined_refs

    try:
        merged["confidence"] = max(
            float(primary.get("confidence") or 0.0), float(secondary.get("confidence") or 0.0)
        )
    except (TypeError, ValueError):
        pass

    secondary_status = str(secondary.get("extraction_status") or "")
    if _STATUS_RANK.get(secondary_status, 0) > _STATUS_RANK.get(
        str(merged.get("extraction_status") or ""), 0
    ):
        merged["extraction_status"] = secondary_status

    merged["_merged_split_fact"] = True
    return merged


def _merge_split_fact_items(
    items: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    category: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Fusiona ítems que en realidad son UN solo hecho partido en fragmentos."""
    if len(items) < 2:
        return items

    grounding_cache = [_grounding_chunk_ids_for_item(item, chunks) for item in items]
    consumed = [False] * len(items)
    result: list[dict[str, Any]] = []
    merge_count = 0

    for i, base_item in enumerate(items):
        if consumed[i]:
            continue
        current = base_item
        current_chunk_ids = grounding_cache[i]

        for j in range(i + 1, len(items)):
            if consumed[j]:
                continue
            other = items[j]
            shared_chunk_ids = current_chunk_ids & grounding_cache[j]
            if not shared_chunk_ids:
                continue
            if not (_has_weak_identity(current) or _has_weak_identity(other)):
                continue

            if _has_weak_identity(current) and not _has_weak_identity(other):
                primary, secondary = other, current
            else:
                primary, secondary = current, other

            current = _merge_two_items(primary, secondary)
            current_chunk_ids = current_chunk_ids | grounding_cache[j]
            consumed[j] = True
            merge_count += 1

        result.append(current)

    if merge_count:
        logger.info(
            "merged_split_fact_items",
            correlation_id=correlation_id,
            category=category,
            merges=merge_count,
            original_count=len(items),
            final_count=len(result),
        )

    return result


def _top_level_section(section_path: Any) -> str:
    """Primer nivel de `section_path`/`heading_path` (ej. "ANEXO V" de
    "ANEXO V > 4. PLAN DE TRABAJO"). Deliberadamente no busca ninguna palabra
    fija ("anexo", "apéndice", etc.) -- toma el heading tal cual lo detectó
    Document Intelligence al procesar el PDF, sea cual sea el vocabulario del
    pliego. "general" (la sección catch-all para contenido sin heading propio)
    no cuenta como unidad identificable: no se debe fusionar nada bajo ella.
    """
    if not section_path:
        return ""
    top = str(section_path).split(">")[0].strip()
    if not top or top.strip().lower() == "general":
        return ""
    return top


def _chunk_section_index(
    chunks: list[dict[str, Any]],
) -> tuple[dict[str, tuple[str, str]], dict[str, set[str]]]:
    """Indexa los chunks recuperados para poder resolver, a partir de un
    `chunk_id` o un `document_id`, a qué "unidad documental" (documento +
    sección de primer nivel) pertenecen.

    Devuelve:
    - `chunk_by_id`: chunk_id -> (document_id, sección de primer nivel)
    - `sections_by_document`: document_id -> {secciones de primer nivel
      distintas presentes en ese documento}. Un documento con más de una
      sección de primer nivel (ej. el pliego general, que trae "ANEXO I" y
      además "COTIZACIÓN DE OPCIONALES OBLIGATORIO" como secciones propias)
      es ambiguo para fusionar ítems sin cita verificada -- se usa para
      decidir cuándo NO adivinar (ver `_item_section_key`).
    """
    chunk_by_id: dict[str, tuple[str, str]] = {}
    sections_by_document: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
        document_id = str(chunk.get("document_id") or "")
        section = _top_level_section(chunk.get("section_path") or chunk.get("heading_path"))
        if chunk_id:
            chunk_by_id[chunk_id] = (document_id, section)
        if document_id and section:
            sections_by_document[document_id].add(section)
    return chunk_by_id, sections_by_document


_ANEXO_ID_RE = re.compile(
    r"\b(?:anexo|apendice|ap[eé]ndice|formulario|planilla|modelo)\s+"
    r"(?:n[°ºo.]*\s*)?([ivxlcdm]+|[a-z]|\d{1,3})\b",
    re.IGNORECASE,
)


def _anexo_identifier(item: dict[str, Any]) -> str:
    """Identificador del anexo dentro de su sección ('anexo ii', 'formulario 5').
    Dos anexos DISTINTOS listados en la misma sección ('Forman parte los Anexos
    I, II y III') no son la misma unidad y no deben fusionarse -- este componente
    del key los separa. Si no hay identificador reconocible, devuelve '' y el
    comportamiento vuelve a ser el histórico (fusiona fantasmas de la sección)."""
    m = _ANEXO_ID_RE.search(_normalize_for_grounding(str(item.get("valor") or "")))
    return m.group(1).lower() if m else ""


def _item_section_key(
    item: dict[str, Any],
    chunk_by_id: dict[str, tuple[str, str]],
    sections_by_document: dict[str, set[str]],
) -> tuple[str, str, str] | None:
    """(document_id, sección de primer nivel) de un ítem, o `None` si no se
    puede determinar con confianza.

    Primero intenta a partir de una cita YA VERIFICADA (la fuente más
    confiable: el `chunk_id` es real y su `section_path` también). Si el
    ítem no tiene ninguna cita verificada (`source_references` vacío -- el
    caso típico de un "anexo" fantasma que el LLM generó sin poder citarlo),
    cae al `document_id` de origen (ver tag `_source_document_id` en
    `run_extractor`) -- pero SOLO si ese documento tiene una única sección de
    primer nivel. Si el documento mezcla más de una sección, no hay forma
    confiable de saber a cuál pertenece el ítem fantasma -- se deja sin
    fusionar antes que arriesgarse a mezclar dos unidades distintas.
    """
    anexo_id = _anexo_identifier(item)

    for ref in item.get("source_references") or []:
        if not isinstance(ref, dict):
            continue
        chunk_id = str(ref.get("chunk_id") or "")
        if chunk_id in chunk_by_id:
            document_id, section = chunk_by_id[chunk_id]
            if document_id and section:
                return (document_id, section, anexo_id)

    source_document_id = item.get("_source_document_id")
    if source_document_id:
        candidate_sections = sections_by_document.get(str(source_document_id)) or set()
        if len(candidate_sections) == 1:
            return (str(source_document_id), next(iter(candidate_sections)), anexo_id)

    return None


def _merge_items_by_document_section(
    items: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    category: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Fusiona ítems que en realidad son la MISMA unidad documental (mismo
    documento + misma sección de primer nivel ya detectada por Document
    Intelligence), sin importar cómo el LLM decidió nombrarlos ni en cuántos
    pedazos los partió.

    Diferencia con `_merge_split_fact_items`: ese mecanismo solo fusiona
    ítems que comparten una cita verificada en común. Este agarra también el
    caso de ítems SIN ninguna cita verificada -- típicamente `partial` +
    `_warning="cita_no_verificada"` -- que el LLM generó a partir de un
    índice interno de la sección (ej. "1. Características Generales",
    "2. Presentación Técnica...") sin poder citar contenido real de cada
    entrada. Hallazgo 2026-08-24 sobre `anexos_obligatorios`: un mismo Anexo
    V, mismos chunks, dio entre 2 y 5 ítems según la corrida -- de esos, solo
    1 tenía cita verificada; el resto eran fantasmas de la misma unidad.

    Deliberadamente no depende de ninguna palabra fija ("anexo", "apéndice",
    "complemento", números romanos, etc.): la clave de fusión es 100%
    estructural, así que funciona igual sin importar el vocabulario o el
    esquema de numeración del pliego. Ver `_DOCUMENT_SECTION_MERGE_CATEGORIES`
    para qué categorías la usan -- no todas: en categorías donde varios
    hechos distintos comparten legítimamente sección (ej. garantías), esto
    NO debe aplicarse.
    """
    if len(items) < 2:
        return items

    chunk_by_id, sections_by_document = _chunk_section_index(chunks)

    groups: dict[tuple[str, str], list[int]] = {}
    for i, item in enumerate(items):
        key = _item_section_key(item, chunk_by_id, sections_by_document)
        if key is None:
            continue
        groups.setdefault(key, []).append(i)

    merged_by_index: dict[int, dict[str, Any]] = {}
    consumed_indices: set[int] = set()
    for _key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        current = items[idxs[0]]
        for idx in idxs[1:]:
            current = _merge_two_items(current, items[idx])
        merged_by_index[idxs[0]] = current
        consumed_indices.update(idxs)

    if not merged_by_index:
        return items

    result: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if i in merged_by_index:
            result.append(merged_by_index[i])
        elif i in consumed_indices:
            continue
        else:
            result.append(item)

    logger.info(
        "merged_items_by_document_section",
        correlation_id=correlation_id,
        category=category,
        groups_merged=len(merged_by_index),
        original_count=len(items),
        final_count=len(result),
    )
    return result


def _group_chunks_by_document(chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Agrupa los chunks recuperados por `document_id`, preservando el orden
    en que llegaron dentro de cada grupo (que ya viene ordenado por
    relevancia desde el retrieval).

    Usado por el extractor map-reduce (ver `run_extractor`): partir por
    documento en vez de mandar todo junto en un solo llamado al LLM.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        document_id = str(chunk.get("document_id") or "sin_documento")
        groups.setdefault(document_id, []).append(chunk)
    return groups
