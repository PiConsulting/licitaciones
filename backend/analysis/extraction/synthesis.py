from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.extractors import base as extractors_base
from analysis.extraction.schemas import CITATION_MIN_CHARS, CategoryNarrative, RawCategoryNarrative, CONFIDENCE_NO_EVIDENCE

# FIX CRÍTICO (2026-08): Import del módulo de highlight pre-computado
try:
    from analysis.extraction.highlight import compute_highlights_for_sources
    HIGHLIGHT_AVAILABLE = True
except ImportError:
    # PyMuPDF no instalado - highlight no disponible pero el sistema funciona
    HIGHLIGHT_AVAILABLE = False
    compute_highlights_for_sources = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"

CATEGORY_LABELS = {
    "objeto_alcance": "Objeto y Alcance",
    "requisitos_admisibilidad": "Requisitos de Admisibilidad",
    "garantias": "Garantías",
    "plazos_clave": "Plazos Clave",
    "criterios_evaluacion": "Criterios de Evaluación",
    "causales_rechazo": "Causales de Rechazo",
    "anexos_obligatorios": "Anexos Obligatorios",
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
        "- Devolver unicamente hitos clave: apertura, mantenimiento de oferta, entrega/ejecucion, consultas e impugnaciones.\n"
        "- No inferir fechas; usar solo lo textual extraido.\n"
        "- Preferir `bullet_list` con etiquetas breves por hito (ej: 'Apertura: 14/09/2026 10:00 hs')."
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
}

# Categorias que se muestran como respuesta narrativa en la UI. Distinto de
# `CANONICAL_CATEGORY_PROMPT_MAP` (que incluye tambien `identificacion_procedimiento`,
# usada solo para el titulo/subtitulo del analisis, nunca como una tarjeta de
# categoria propia) para no gastar una llamada LLM de sintesis en una narrativa
# que el frontend nunca renderiza.
NARRATIVE_CATEGORIES = tuple(CATEGORY_LABELS)

_USABLE_STATUSES = {"success", "partial", "not_applicable"}


def _normalize_text_for_comparison(text: str) -> str:
    """Normaliza texto para comparación: elimina acentos, espacios múltiples, lowercase."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _dedupe_narrative_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica sources en narrative usando mismo criterio que graph.py:
    mismo document_id + page_number + citation normalizada = misma fuente.
    Mantiene el primer ID encontrado para cada fuente única."""
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
            # Ya existe esta fuente, mapear el ID original al ID canónico
            canonical_id = seen[key]
            id_mapping[original_id] = canonical_id
        else:
            # Nueva fuente única
            new_id = len(deduped)
            seen[key] = new_id
            id_mapping[original_id] = new_id
            deduped_source: dict[str, Any] = {
                "id": new_id,
                "document_id": doc_id,
                "page_number": page,
                "citation": citation,
            }
            # La marca de cita no verificada se pierde si se reconstruye el dict
            # desde cero: la fuente llegaba al usuario sin ninguna señal de que
            # no se pudo respaldar contra los chunks.
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
        stubs.append(
            {
                "document_id": str(ref.get("document_id", "")),
                "page_number": int(ref.get("page_number", 0) or 0),
                "citation": citation,
            }
        )
    return stubs


def _resolve_narrative_sources(
    raw: RawCategoryNarrative,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> CategoryNarrative:
    """Traduce la salida cruda del LLM (bloques con `item_refs`) a un
    `CategoryNarrative` (bloques con `source_ids` + `sources`), resolviendo
    cada referencia contra los `source_references` PROPIOS del item apuntado.

    Esto es lo que hace estructuralmente imposible que la fuente de un bloque
    sea la evidencia de un item distinto: `sources` solo se puede poblar desde
    `item_stubs[i]` para los indices `i` que el LLM efectivamente referencio,
    nunca desde un pool global de la categoria. Un bloque/bullet/fila cuyos
    `item_refs` no resuelven a ningun source valido se descarta entero — "no
    hay fuente, no hay afirmacion" aplicado en codigo, no delegado al prompt."""
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
                retained_blocks.append({"type": "table", "headers": block.headers, "rows": kept_rows})

    # Dedup final: misma clave que ya usa el resto del pipeline (documento +
    # pagina + cita normalizada). Dos items distintos que citan literalmente
    # el mismo fragmento colapsan a una sola source referenciada por ambos.
    deduped_sources, id_mapping = _dedupe_narrative_sources(all_stubs)

    def remap(block_data: dict[str, Any]) -> dict[str, Any]:
        if isinstance(block_data.get("source_ids"), list):
            block_data["source_ids"] = [id_mapping.get(sid, sid) for sid in block_data["source_ids"]]
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

    return CategoryNarrative.model_validate({"blocks": blocks_data, "sources": deduped_sources})


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
    prompt_path = Path(__file__).resolve().parent / "prompts" / RESPONSE_BASE_PROMPT_FILE
    return prompt_path.read_text(encoding="utf-8")


def _serialize_items(items: list[dict[str, Any]]) -> str:
    """Serializa los items para el prompt, exponiendo `item_index` (posicion
    0-based) explicitamente: es el unico identificador que el LLM puede usar
    en `item_refs`, y depender de que cuente bien la posicion en un array es
    mas fragil que dárselo ya resuelto."""
    indexed = [{"item_index": position, **item} for position, item in enumerate(items)]
    return json.dumps(indexed, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
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
        )

        raw, token_usage = extractors_base._call_llm(messages=[("human", prompt)], correlation_id=correlation_id)
        raw_narrative = RawCategoryNarrative.model_validate(raw)

        # Resuelve item_refs -> source_references propios de cada item. Nunca
        # confia en texto o ids que el LLM haya podido inventar.
        narrative = _resolve_narrative_sources(raw_narrative, items, correlation_id=correlation_id)
        if not narrative.blocks:
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


def enrich_narrative_with_highlights(
    narrative: CategoryNarrative,
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
) -> CategoryNarrative:
    """Enriquece una CategoryNarrative con coordenadas de highlight pre-computadas.
    
    FIX CRÍTICO (2026-08): Resuelve el problema de highlight frágil identificado
    en la auditoría RAG. En lugar de usar heurísticas de matching en el frontend,
    pre-computamos las coordenadas exactas usando PyMuPDF.
    
    Args:
        narrative: CategoryNarrative ya construida (output de run_synthesis)
        document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF
        correlation_id: ID para logging
    
    Returns:
        CategoryNarrative con sources enriquecidas (highlight_regions poblado)
    
    Note:
        Si PyMuPDF no está disponible o falla el cálculo, las sources conservan
        highlight_regions=[] (lista vacía) y el sistema funciona normalmente sin
        highlights. El frontend debe manejar este caso gracefully.
    """
    if not HIGHLIGHT_AVAILABLE:
        logger.info(
            "highlight_skipped_not_available",
            correlation_id=correlation_id,
            message="PyMuPDF no instalado - highlights no disponibles",
        )
        return narrative
    
    if not narrative.sources:
        return narrative
    
    try:
        # Convertir sources a dict para modificar
        sources_data = [source.model_dump() for source in narrative.sources]
        
        # Enriquecer con highlights
        enriched_sources_data = compute_highlights_for_sources(
            sources=sources_data,
            document_id_to_blob_path=document_id_to_blob_path,
            correlation_id=correlation_id,
        )
        
        # Reconstruir narrative con sources enriquecidas
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
