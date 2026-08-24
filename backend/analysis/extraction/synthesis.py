from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.extractors import base as extractors_base
from analysis.extraction.schemas import (
    CITATION_MIN_CHARS,
    CategoryNarrative,
    RawCategoryNarrative,
    CONFIDENCE_NO_EVIDENCE,
)

try:
    from analysis.extraction.highlight import compute_highlights_for_sources

    HIGHLIGHT_AVAILABLE = True
except ImportError:
    HIGHLIGHT_AVAILABLE = False
    compute_highlights_for_sources = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"
OUTPUT_SCHEMA_FILE = "_output_schema.txt"

CATEGORY_LABELS = {
    "objeto_alcance": "Objeto y Alcance",
    "requisitos_admisibilidad": "Requisitos de Admisibilidad",
    "garantias": "Garantías",
    "plazos_clave": "Plazos Clave",
    "criterios_evaluacion": "Criterios de Evaluación",
    "causales_rechazo": "Causales de Rechazo",
    "anexos_obligatorios": "Anexos Obligatorios",
    "riesgos": "Riesgos",
}

CATEGORY_OUTPUT_CONTRACTS = {
    "objeto_alcance": (
        "- Devolver exactamente QUE se licita en 2-3 lineas maximo.\n"
        "- No incluir modalidad, lugar de entrega, plazos, garantias, criterios, causales, anexos ni requisitos.\n"
        "- Emitir UN solo bloque `paragraph` con sintesis directa, sin introducciones largas."
    ),
    "requisitos_admisibilidad": (
        "- Devolver solo documentacion obligatoria de admisibilidad (habilitaciones, antecedentes, certificaciones)\n"
        "  cuya falta puede rechazar la oferta de entrada.\n"
        "- Usar `bullet_list` con items cortos y accionables (ideal <= 14 palabras).\n"
        "- Estilo preferido: verbo + documento (ej: 'Presentar constancia RUP vigente')."
    ),
    "garantias": (
        "- Devolver solo garantias financieras (mantenimiento de oferta, cumplimiento de contrato y similares).\n"
        "- Incluir monto/porcentaje y forma de constitucion cuando exista evidencia.\n"
        "- No mezclar con garantias tecnicas del producto.\n"
        "- Priorizar formato escaneable: una garantia por item, sin texto ornamental."
    ),
    "plazos_clave": (
        "- Usar `bullet_list`, un item por plazo distinto.\n"
        "- Cada bullet debe usar el `texto_original` del item, que ya contiene descripcion\n"
        "  completa del plazo con contexto (QUE plazo es, CUANDO se cuenta, QUIEN lo ejecuta).\n"
        "- FIX (2026-08-21): El campo `tipo` ahora es opcional. NO usar 'tipo' para etiquetar\n"
        "  bullets. Escribir el texto_original directamente, sin prefijos artificiales.\n"
        "- Si el hito tiene fecha/hora limpia y sin condicion (ej: apertura, presentacion),\n"
        "  podés reformular brevemente: 'Apertura: 14/09/2026 10:00 hs'.\n"
        "- Si el plazo depende de una condicion o disparador (ej: 'a partir de la recepcion\n"
        "  provisoria de cada hito...'), expresar la oracion completa y bien formada, sin\n"
        "  perder a que se refiere el plazo ni la condicion que lo activa.\n"
        "- Si dos bullets terminarian describiendo el mismo plazo con fragmentos distintos\n"
        "  de la misma oracion (la condicion en uno, la duracion en otro), consolidalos\n"
        "  en un solo bullet.\n"
        "- NUNCA empezar un bullet con 'Otro:' ni usar clasificaciones tecnicas internas\n"
        "  como etiquetas. El texto_original ya es descriptivo y auto-contenido.\n"
        "  Ejemplo correcto:\n"
        "  'La Provincia dispone de un plazo maximo de 15 dias corridos desde la recepcion\n"
        "  provisoria de cada hito del Plan de Entrega y Servicios para otorgar la F.A.D.'\n"
        "- No inferir fechas; usar solo lo textual extraido."
    ),
    "criterios_evaluacion": (
        "- Devolver como se pondera precio vs tecnica y si existe puntaje minimo.\n"
        "- Si hay varios factores, usar `bullet_list` o `table` segun comparabilidad.\n"
        "- Mantener redaccion breve (no explicar contexto ya obvio)."
    ),
    "causales_rechazo": (
        "- Esta es la categoria mas critica: listar motivos de rechazo formal que descalifican sin evaluar oferta.\n"
        "- Priorizar claridad y completitud de causales, sin mezclar requisitos no descalificantes.\n"
        "- Usar `bullet_list` con formula breve: 'Rechazo si ...' (ideal <= 16 palabras)."
    ),
    "anexos_obligatorios": (
        "- Devolver solo formularios/anexos que deben completarse y presentarse si o si.\n"
        "- No incluir certificados externos ni documentacion de terceros (eso va en admisibilidad).\n"
        "- Formato recomendado: `bullet_list` con nombre de anexo + accion requerida."
    ),
    "riesgos": (
        "- Listar riesgos identificables que puedan afectar la participación o ejecución del contrato.\n"
        "- Incluir consecuencias de incumplimientos (multas, penalizaciones, rescisión).\n"
        "- Usar `bullet_list` con descripción clara y concisa del riesgo.\n"
        "- No duplicar causales de rechazo ni requisitos (van en sus categorías propias)."
    ),
}


NARRATIVE_CATEGORIES = tuple(CATEGORY_LABELS)

_USABLE_STATUSES = {"success", "partial", "not_applicable"}


def _normalize_text_for_comparison(text: str) -> str:
    """Normaliza texto para comparación: elimina acentos, espacios múltiples, lowercase."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _overlap_ratio(needle: str, haystack: str) -> float:
    """Fracción de palabras de `needle` presentes en `haystack`. Sólo se usa
    para elegir, entre las citas verificadas de un mismo item, cuál se parece
    más al texto que transcribió el LLM."""
    needle_words = set(_normalize_text_for_comparison(needle).split())
    if not needle_words:
        return 0.0
    haystack_words = set(_normalize_text_for_comparison(haystack).split())
    return len(needle_words & haystack_words) / len(needle_words)


def _stub_for_evidence(
    evidence: Any,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> tuple[dict[str, Any], str] | None:
    """Ancla una evidencia del LLM a una cita YA VERIFICADA del item que ella
    misma dice respaldar. Devuelve `(stub, citation)` o None.
    """
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


def _count_raw_narrative_elements(raw: RawCategoryNarrative) -> int:
    """Cantidad de afirmaciones ATÓMICAS que produjo el LLM de síntesis.

    Cuenta párrafos, bullets y filas por separado -- no bloques de primer
    nivel. Es la unidad correcta para medir pérdida: un `bullet_list` puede
    conservarse como bloque y aun así haber perdido 7 de sus 8 bullets, y
    contar bloques no lo detectaría (ver `_resolve_narrative_sources`).
    """
    total = 0
    for block in raw.blocks:
        if block.type == "paragraph":
            total += 1
        elif block.type == "bullet_list":
            total += len(block.items)
        elif block.type == "table":
            total += len(block.rows)
    return total


def _count_narrative_elements(narrative: CategoryNarrative) -> int:
    """Misma cuenta que `_count_raw_narrative_elements`, sobre la salida ya
    resuelta. La diferencia entre ambas es exactamente lo que se descartó por
    no poder respaldarlo con una fuente."""
    total = 0
    for block in narrative.blocks:
        if block.type == "paragraph":
            total += 1
        elif block.type == "bullet_list":
            total += len(block.items)
        elif block.type == "table":
            total += len(block.rows)
    return total


def _dedupe_narrative_sources(
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """Deduplica sources en narrative usando normalización de texto."""
    seen: dict[tuple[str, int, str], int] = {}
    deduped: list[dict[str, Any]] = []
    id_mapping: dict[int, int] = {}

    for source in sources:
        doc_id = str(source.get("document_id", ""))
        page = int(source.get("page_number", 0) or 0)
        citation = str(source.get("citation", ""))
        normalized_citation = _normalize_text_for_comparison(citation)
        key = (doc_id, page, normalized_citation)

        original_id = int(source.get("id", 0))

        if key in seen:
            canonical_id = seen[key]
            id_mapping[original_id] = canonical_id
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

            if source.get("block_id"):
                deduped_source["block_id"] = str(source.get("block_id"))

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


def _empty_category_narrative(category_label: str) -> CategoryNarrative:
    """Mensaje canonico de "sin evidencia" para una categoria, armado en
    codigo -- nunca por el LLM. Cierra el loophole por el que un bloque sin
    fuentes reales podia llegar disfrazado de la excepcion "sin contenido
    util" que antes autorizaba el prompt."""
    return CategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": f"No se encontró información sobre {category_label} en los documentos del pliego.",
                    "confidence_level": CONFIDENCE_NO_EVIDENCE,  # Constante desde schemas
                    "source_ids": [],
                }
            ],
            "sources": [],
        }
    )


@lru_cache(maxsize=1)
def _load_response_base_prompt() -> str:
    """Carga el prompt base y el schema de output, concatenándolos."""
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    base_prompt = (prompts_dir / RESPONSE_BASE_PROMPT_FILE).read_text(encoding="utf-8")
    output_schema = (prompts_dir / OUTPUT_SCHEMA_FILE).read_text(encoding="utf-8")
    return f"{base_prompt}\n\n---\n\n{output_schema}"


def _serialize_items(items: list[dict[str, Any]]) -> str:
    """Serializa los items para el prompt, exponiendo `item_index` (posicion
    0-based) explicitamente: es el unico identificador que el LLM puede usar
    en `item_refs`, y depender de que cuente bien la posicion en un array es
    mas fragil que dárselo ya resuelto."""
    indexed = [{"item_index": position, **item} for position, item in enumerate(items)]
    return json.dumps(indexed, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


_CONFLICT_CATEGORY_TO_NARRATIVE = {
    "plazos": "plazos_clave",
    "garantias": "garantias",
}


def _conflict_block(category_key: str, conflicts: list[dict[str, Any]] | None) -> str:
    """El bloque de prompt que le avisa al redactor qué datos se contradicen."""
    if not conflicts:
        return "(sin contradicciones detectadas)"

    relevantes = [
        conflict
        for conflict in conflicts
        if _CONFLICT_CATEGORY_TO_NARRATIVE.get(str(conflict.get("category", ""))) == category_key
    ]
    if not relevantes:
        return "(sin contradicciones detectadas)"

    lineas: list[str] = []
    for conflict in relevantes:
        valores = []
        for item in conflict.get("values", []) or []:
            etiqueta = (
                item.get("valor")
                or item.get("fecha")
                or item.get("expresion_relativa")
                or item.get("monto_porcentaje")
                or item.get("monto_valor")
            )
            paginas = sorted(
                {
                    str(ref.get("page_number"))
                    for ref in (item.get("source_references") or [])
                    if ref.get("page_number")
                }
            )
            ubicacion = f" (pág. {', '.join(paginas)})" if paginas else ""
            if etiqueta is not None:
                valores.append(f"{etiqueta}{ubicacion}")
        if valores:
            lineas.append(
                f"- `{conflict.get('tipo', 'dato')}`: {conflict.get('reason', 'valores en conflicto')} "
                f"-> {' vs. '.join(valores)}"
            )

    return "\n".join(lineas) if lineas else "(sin contradicciones detectadas)"


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
    chunks_by_id: dict[str, dict] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> tuple[CategoryNarrative, dict[str, int]] | None:
    """Convierte los items ya extraidos de una categoria en una respuesta de
    experto: bloques en lenguaje natural (parrafo/lista/tabla), nunca metadata
    cruda. Devuelve None si no hay contenido util o si la sintesis falla por
    cualquier motivo (LLM, parseo, validacion) — el llamador (grafo) y el
    frontend ya tienen fallback, asi que una categoria nunca se queda sin
    respuesta por un fallo puntual de este paso."""
    if not items or not _has_usable_content(items):
        return None

    try:
        category_label = CATEGORY_LABELS.get(category_key, category_key)
        category_contract = CATEGORY_OUTPUT_CONTRACTS.get(
            category_key,
            "- Priorizar exactitud, concision y separacion estricta por categoria.",
        )
        prompt = (
            _load_response_base_prompt()
            .replace("{items_json}", _serialize_items(items))
            .replace("{category_label}", category_label)
            .replace("{category_output_contract}", category_contract)
            .replace("{conflicts_block}", _conflict_block(category_key, conflicts))
        )

        raw, token_usage = extractors_base._call_llm(
            messages=[("human", prompt)], correlation_id=correlation_id
        )
        raw_narrative = RawCategoryNarrative.model_validate(raw)

        narrative = _resolve_narrative_sources(
            raw_narrative,
            items,
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
        )
        if not narrative.blocks:
            logger.error(
                "synthesis_fell_back_to_empty_narrative_despite_usable_items",
                correlation_id=correlation_id,
                category=category_key,
                items_count=len(items),
                items_with_sources=sum(1 for item in items if item.get("source_references")),
                raw_blocks=len(raw_narrative.blocks),
                raw_evidence=len(raw_narrative.evidence),
                impact="el usuario verá 'No se encontró información' para una categoría que sí tiene datos extraídos",
            )
            narrative = _empty_category_narrative(category_label)

        logger.info(
            "synthesis_completed",
            correlation_id=correlation_id,
            category=category_key,
            blocks=len(narrative.blocks),
            sources=len(narrative.sources),
        )
        return narrative, token_usage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "synthesis_failed",
            correlation_id=correlation_id,
            category=category_key,
            error=str(exc),
        )
        return None


def _build_chunks_index_from_search(
    analysis_id: str, correlation_id: str
) -> dict[tuple[str, int], list[dict]]:
    """Construye índice de chunks por (document_id, page_number) desde Azure Search."""
    try:
        from shared.ports.azure_search import fetch_all_analysis_chunks

        all_chunks, truncated = fetch_all_analysis_chunks(analysis_id)
        chunks_by_doc_page: dict[tuple[str, int], list[dict]] = {}
        for chunk in all_chunks:
            doc_id = chunk.get("document_id")
            page = chunk.get("page_number")
            if not doc_id or not page:
                continue
            key = (str(doc_id), int(page))
            if key not in chunks_by_doc_page:
                chunks_by_doc_page[key] = []
            chunks_by_doc_page[key].append(chunk)

        logger.info(
            "chunks_index_built",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            total_chunks=len(all_chunks),
            unique_pages=len(chunks_by_doc_page),
            truncated=truncated,
        )

        return chunks_by_doc_page

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chunks_index_build_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            error=str(exc),
            message="Highlight no disponible - no se pudo construir índice de chunks",
        )
        return {}


def enrich_narrative_with_highlights(
    narrative: CategoryNarrative,
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
    *,
    category_key: str | None = None,
    analysis_id: str | None = None,
    chunks_by_doc_page: dict[tuple[str, int], list[dict]] | None = None,
) -> CategoryNarrative:
    """Enriquece una CategoryNarrative con coordenadas de highlight pre-computadas."""
    if not HIGHLIGHT_AVAILABLE:
        logger.info(
            "highlight_skipped_not_available",
            correlation_id=correlation_id,
            message="PyMuPDF no instalado - highlights no disponibles",
        )
        return narrative

    if not narrative.sources:
        return narrative

    if chunks_by_doc_page is None:
        if analysis_id:
            logger.info(
                "highlight_building_own_chunks_index",
                correlation_id=correlation_id,
                category_key=category_key,
                reason="no se recibió chunks_by_doc_page; se construye localmente",
            )
            chunks_by_doc_page = _build_chunks_index_from_search(analysis_id, correlation_id)
        else:
            chunks_by_doc_page = {}
            logger.warning(
                "highlight_skipped_no_analysis_id",
                correlation_id=correlation_id,
                message="analysis_id no disponible - highlights no se calcularán",
            )

    try:
        sources_data = [source.model_dump() for source in narrative.sources]
        enriched_sources_data = compute_highlights_for_sources(
            sources=sources_data,
            document_id_to_blob_path=document_id_to_blob_path,
            correlation_id=correlation_id,
            category_key=category_key,
            chunks_by_doc_page=chunks_by_doc_page,
        )
        narrative_data = narrative.model_dump()
        narrative_data["sources"] = enriched_sources_data

        return CategoryNarrative.model_validate(narrative_data)

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "highlight_enrichment_failed",
            correlation_id=correlation_id,
            error=str(exc),
            message="Highlights no disponibles - narrative devuelta sin modificar",
        )
        return narrative
