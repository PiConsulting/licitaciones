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


_PLACEHOLDER_VALOR_MARKERS = (
    "no especificado",
    "no se especifica",
    "no encontrado",
    "no se encontro",
    "not_found",
    "no aplica",
    "sin informacion",
)


def _looks_like_placeholder_valor(item: dict[str, Any]) -> bool:
    """`True` si el `valor` del ítem es un placeholder de "no hay dato"
    (cualquiera de las frases típicas que ya usan los prompts para eso), no
    un dato real."""
    valor = _normalize_for_grounding(str(item.get("valor") or ""))
    if not valor:
        return True
    return any(marker in valor for marker in _PLACEHOLDER_VALOR_MARKERS)


def _merge_singleton_tipo_duplicates(
    items: list[dict[str, Any]],
    singleton_tipos: set[str],
    *,
    category: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Colapsa a UN SOLO ítem los `tipo` que el propio prompt de la categoría
    ya declara como singleton ("UN ítem X", ver `objeto_alcance.txt`).

    FIX (2026-09-14, Fase 2 de la auditoría RAG): el dedup existente
    (`_merge_duplicate_items_by_key` en `graph/nodes.py`) fusiona por
    `(tipo, valor)` -- solo detecta duplicados con el MISMO texto. No detecta
    dos ítems del MISMO tipo singleton con valores DISTINTOS (ej. uno con el
    dato real y otro con un placeholder "No especificado"), que el map-reduce
    por lote (`_split_oversized_groups`, ver `base.py`) puede producir: cada
    lote ve un subconjunto distinto de chunks, y un lote que no tiene el dato
    en su subconjunto igual emite el ítem singleton con un placeholder,
    mientras otro lote sí lo encuentra. Genérico por diseño: qué tipos son
    singleton lo decide el CALLER (a partir de lo que ya declara el prompt de
    cada categoría), esta función no sabe nada de ningún pliego en particular
    -- solo sabe fusionar duplicados de un `tipo` que se supone que aparece
    una sola vez.

    Si hay algún candidato con dato real (no placeholder), los placeholders
    del mismo tipo se descartan antes de fusionar -- ver `_looks_like_placeholder_valor`.
    Si TODOS son placeholder, se conserva uno (no se pierde el tipo)."""
    if len(items) < 2:
        return items

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for item in items:
        tipo = str(item.get("tipo") or "")
        if tipo in singleton_tipos:
            grouped[tipo].append(item)
        else:
            passthrough.append(item)

    if not any(len(group) > 1 for group in grouped.values()):
        return items

    result = list(passthrough)
    merges = 0
    for tipo, group in grouped.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        substantive = [g for g in group if not _looks_like_placeholder_valor(g)]
        candidates = substantive or group
        merged = candidates[0]
        for extra in candidates[1:]:
            merged = _merge_two_items(merged, extra)
        result.append(merged)
        merges += 1

    if merges:
        logger.info(
            "merged_singleton_tipo_duplicates",
            correlation_id=correlation_id,
            category=category,
            merges=merges,
            original_count=len(items),
            final_count=len(result),
        )
    return result


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
) -> tuple[str, ...] | None:
    """Clave de fusión de un ítem, o `None` si no se puede determinar con
    confianza.

    FIX (2026-09-14, Fase 2 de la auditoría RAG): un anexo NUMERADO ("Anexo
    II") tiene una sola identidad real en todo el pliego, sin importar en
    qué documento subido aparece -- puede estar mencionado en el índice del
    pliego principal (documento A) y, por separado, ser su propio archivo
    subido con el contenido real (documento B). Antes la clave incluía
    SIEMPRE `document_id`, así que esas dos apariciones del mismo anexo
    nunca se fusionaban -- medido en un pliego real (multi-documento, 6
    anexos numerados): cada uno salía duplicado. Cuando `_anexo_identifier`
    reconoce un identificador, se agrupa SOLO por él -- global al pliego,
    no al documento.

    Para los "fantasmas" SIN identificador reconocible (el caso original que
    esta función ya cubría: el LLM generó un ítem a partir de un índice
    interno de la sección, sin poder citar contenido real de cada entrada),
    se mantiene el criterio anterior: (document_id, sección de primer nivel)
    a partir de una cita YA VERIFICADA, o del `document_id` de origen si ese
    documento tiene una única sección de primer nivel. Ahí SÍ hace falta
    acotar a un documento -- sin identificador no hay forma confiable de
    saber si dos fantasmas de documentos distintos son la misma unidad o
    no, así que se prefiere no fusionar antes que arriesgarse.
    """
    anexo_id = _anexo_identifier(item)
    if anexo_id:
        return (anexo_id,)

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

    groups: dict[tuple[str, ...], list[int]] = {}
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
    """Agrupa los chunks recuperados por `document_id`.

    Usado por el extractor map-reduce (ver `run_extractor`): partir por
    documento en vez de mandar todo junto en un solo llamado al LLM.

    FIX (2026-09-11, diagnóstico de no-determinismo en garantías): antes
    cada grupo quedaba en el orden de llegada del retrieval (por score de
    relevancia), no en el orden real del documento. Para una categoría que
    pide "enumerá TODAS las garantías/plazos/...", leer los fragmentos
    salteados en vez de en el orden en que aparecen en el pliego dificulta
    el barrido sistemático que necesita el LLM para no saltearse ninguno.
    Se reordena cada grupo por `chunk_index` (posición real en el
    documento) -- no cambia QUÉ chunks entran, solo en qué orden se leen.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        document_id = str(chunk.get("document_id") or "sin_documento")
        groups.setdefault(document_id, []).append(chunk)

    for group_chunks in groups.values():
        group_chunks.sort(key=lambda c: int(c.get("chunk_index", 0) or 0))

    return groups


def _split_oversized_groups(
    groups: dict[str, list[dict[str, Any]]], *, max_chunks_per_call: int
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Parte cada grupo de `_group_chunks_by_document` en sub-lotes de a lo
    sumo `max_chunks_per_call` chunks (mismo `document_id`, varias llamadas).

    FIX (2026-09-11): el map-reduce por documento (2026-08-21) reduce
    cuánto texto compite por atención en un mismo llamado al LLM -- pero
    solo si el pliego tiene VARIOS documentos. Un pliego de un solo
    documento (el caso más común: municipios, organismos chicos) sigue
    mandando todo el `top_k` de la categoría (hasta 35 chunks en garantías)
    en un único llamado, exactamente el escenario "lost in the middle" que
    el map-reduce quiso evitar. Partir también DENTRO de un documento
    generaliza el mismo fix al caso de un solo documento. Los chunks ya
    vienen ordenados por `chunk_index` (ver `_group_chunks_by_document`),
    así que cada sub-lote es un tramo contiguo del documento, no una
    mezcla salteada. `max_chunks_per_call <= 0` desactiva el split
    (comportamiento previo: un llamado por documento, sin importar el
    tamaño)."""
    if max_chunks_per_call <= 0:
        return list(groups.items())

    batches: list[tuple[str, list[dict[str, Any]]]] = []
    for document_id, group_chunks in groups.items():
        if len(group_chunks) <= max_chunks_per_call:
            batches.append((document_id, group_chunks))
            continue
        for start in range(0, len(group_chunks), max_chunks_per_call):
            batches.append((document_id, group_chunks[start : start + max_chunks_per_call]))
    return batches
