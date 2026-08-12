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
OUTPUT_SCHEMA_FILE = "_output_schema.txt"

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


def _resolve_from_evidence(
    raw: RawCategoryNarrative,
    chunks_by_id: dict[str, dict],
    *,
    correlation_id: str,
) -> CategoryNarrative:
    """Construye CategoryNarrative desde evidencias textuales del LLM.
    
    Arquitectura nueva (2026-08-12):
    - El LLM devuelve `evidence` con document_id + page_number + texto exacto
    - Este texto se busca en el chunk para extraer chunk_id y validar
    - Solo se resaltan las frases específicas que el LLM citó
    
    Esto resuelve el problema: "retrieved chunks != evidence chunks"
    """
    all_sources: list[dict[str, Any]] = []
    evidence_to_source_id: dict[str, int] = {}
    
    # Construir sources desde evidencias
    for ev in raw.evidence:
        # Buscar chunk por (document_id, page_number) ya que el LLM no tiene chunk_id
        matching_chunks = [
            c for c in chunks_by_id.values()
            if c.get("document_id") == ev.document_id and c.get("page_number") == ev.page_number
        ]
        
        if not matching_chunks:
            logger.warning(
                "evidence_no_matching_chunks",
                correlation_id=correlation_id,
                document_id=ev.document_id,
                page_number=ev.page_number,
                text_preview=ev.text[:50],
            )
            continue
        
        # Buscar el chunk que contiene el texto de evidencia
        chunk = None
        evidence_normalized = _normalize_text_for_comparison(ev.text)
        for candidate in matching_chunks:
            chunk_content = candidate.get("content", "")
            chunk_content_normalized = _normalize_text_for_comparison(chunk_content)
            
            if evidence_normalized in chunk_content_normalized:
                chunk = candidate
                break
        
        if not chunk:
            logger.warning(
                "evidence_text_not_found_in_page",
                correlation_id=correlation_id,
                document_id=ev.document_id,
                page_number=ev.page_number,
                evidence_text=ev.text[:100],
                chunks_checked=len(matching_chunks),
            )
            continue
        
        # Crear source desde evidencia
        evidence_key = f"{chunk['document_id']}-{chunk['page_number']}-{evidence_normalized}"
        
        if evidence_key in evidence_to_source_id:
            # Ya existe esta evidencia, reutilizar
            continue
        
        chunk_id = chunk.get("chunk_id")  # Obtenido del matching, no del LLM
        
        source = {
            "id": len(all_sources),
            "document_id": chunk["document_id"],
            "page_number": chunk["page_number"],
            "citation": ev.text,  # Texto exacto del LLM
            "unverified": False,
            "highlight_regions": [],  # Se computará después
            "chunk_id": chunk_id,  # Para matching posterior con highlight
        }
        
        all_sources.append(source)
        evidence_to_source_id[evidence_key] = source["id"]
    
    # Mapear item_refs de evidencias a source_ids
    def get_source_ids_for_item_refs(item_refs: list[int]) -> list[int]:
        """Encuentra sources que corresponden a estos item_refs."""
        source_ids = []
        for ev in raw.evidence:
            if any(ref in item_refs for ref in ev.item_refs):
                # Buscar chunks que matcheen (document_id, page_number)
                matching_chunks = [
                    c for c in chunks_by_id.values()
                    if c.get("document_id") == ev.document_id and c.get("page_number") == ev.page_number
                ]
                
                chunk = None
                evidence_normalized = _normalize_text_for_comparison(ev.text)
                for candidate in matching_chunks:
                    chunk_content_normalized = _normalize_text_for_comparison(candidate.get("content", ""))
                    if evidence_normalized in chunk_content_normalized:
                        chunk = candidate
                        break
                
                if not chunk:
                    continue
                
                evidence_key = f"{chunk['document_id']}-{chunk['page_number']}-{evidence_normalized}"
                
                source_id = evidence_to_source_id.get(evidence_key)
                if source_id is not None and source_id not in source_ids:
                    source_ids.append(source_id)
        
        return source_ids
    
    # Construir bloques con source_ids
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
            blocks_data.append({
                "type": "paragraph",
                "text": block.text,
                "confidence_level": block.confidence_level,
                "source_ids": source_ids,
            })
        elif block.type == "bullet_list":
            kept_items = []
            for bullet in block.items:
                source_ids = get_source_ids_for_item_refs(bullet.item_refs)
                if not source_ids:
                    continue
                kept_items.append({
                    "text": bullet.text,
                    "confidence_level": bullet.confidence_level,
                    "source_ids": source_ids,
                })
            if kept_items:
                blocks_data.append({"type": "bullet_list", "items": kept_items})
        elif block.type == "table":
            kept_rows = []
            for row in block.rows:
                source_ids = get_source_ids_for_item_refs(row.item_refs)
                if not source_ids:
                    continue
                kept_rows.append({
                    "cells": row.cells,
                    "confidence_level": row.confidence_level,
                    "source_ids": source_ids,
                })
            if kept_rows:
                blocks_data.append({"type": "table", "headers": block.headers, "rows": kept_rows})
    
    logger.info(
        "narrative_resolved_from_evidence",
        correlation_id=correlation_id,
        evidence_count=len(raw.evidence),
        sources_created=len(all_sources),
        blocks_retained=len(blocks_data),
    )
    
    return CategoryNarrative.model_validate({"blocks": blocks_data, "sources": all_sources})


def _dedupe_narrative_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica sources en narrative usando normalización de texto.
    
    FIX CRÍTICO (2026-08-12): NO agrupar por block_id ni combinar citations.
    - Cada citation única es una source separada (permite múltiples highlights del mismo párrafo)
    - Solo deduplica citations literalmente idénticas (mismo documento, página, texto normalizado)
    - NUNCA combina con [...] (eso creaba citations que no existen en el PDF)
    
    Clave de deduplicación: (document_id, page_number, citation_normalizada)
    """
    seen: dict[tuple[str, int, str], int] = {}
    deduped: list[dict[str, Any]] = []
    id_mapping: dict[int, int] = {}

    for source in sources:
        doc_id = str(source.get("document_id", ""))
        page = int(source.get("page_number", 0) or 0)
        citation = str(source.get("citation", ""))
        normalized_citation = _normalize_text_for_comparison(citation)
        
        # Clave: documento + página + texto normalizado (NO usar block_id)
        key = (doc_id, page, normalized_citation)
        
        original_id = int(source.get("id", 0))
        
        if key in seen:
            # Citation duplicada exacta → reusar source existente
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
            # Preservar block_id como metadata (NO para agrupación)
            if source.get("block_id"):
                deduped_source["block_id"] = str(source.get("block_id"))
            
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
        stub = {
            "document_id": str(ref.get("document_id", "")),
            "page_number": int(ref.get("page_number", 0) or 0),
            "citation": citation,
        }
        # FIX (2026-08-11): Incluir block_id si está disponible
        block_id = ref.get("block_id")
        if block_id:
            stub["block_id"] = str(block_id)
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
    
    NUEVO (2026-08-12): Si `raw.evidence` está presente, construye sources
    desde las evidencias (texto exacto del chunk) en vez de item_refs.
    Esto permite highlighting preciso de frases específicas, no párrafos enteros.

    Esto es lo que hace estructuralmente imposible que la fuente de un bloque
    sea la evidencia de un item distinto: `sources` solo se puede poblar desde
    `item_stubs[i]` para los indices `i` que el LLM efectivamente referencio,
    nunca desde un pool global de la categoria. Un bloque/bullet/fila cuyos
    `item_refs` no resuelven a ningun source valido se descarta entero — "no
    hay fuente, no hay afirmacion" aplicado en codigo, no delegado al prompt."""
    
    # NUEVO: Si hay evidencias NO VACÍAS, construir sources desde ahí
    # IMPORTANTE: Solo usar evidence-based si el LLM devolvió evidencias válidas
    if raw.evidence and len(raw.evidence) > 0 and chunks_by_id:
        logger.info(
            "using_evidence_based_resolution",
            correlation_id=correlation_id,
            evidence_count=len(raw.evidence),
        )
        return _resolve_from_evidence(raw, chunks_by_id, correlation_id=correlation_id)
    
    # Flujo estándar: usar item_refs (backward compatible)
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
    """Carga el prompt base y el schema de output, concatenándolos."""
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    base_prompt = (prompts_dir / RESPONSE_BASE_PROMPT_FILE).read_text(encoding="utf-8")
    output_schema = (prompts_dir / OUTPUT_SCHEMA_FILE).read_text(encoding="utf-8")
    
    # Concatenar con separador
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


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
    chunks_by_id: dict[str, dict] | None = None,
) -> tuple[CategoryNarrative, dict[str, int]] | None:
    """Convierte los items ya extraidos de una categoria en una respuesta de
    experto: bloques en lenguaje natural (parrafo/lista/tabla), nunca metadata
    cruda. Devuelve None si no hay contenido util o si la sintesis falla por
    cualquier motivo (LLM, parseo, validacion) — el llamador (grafo) y el
    frontend ya tienen fallback, asi que una categoria nunca se queda sin
    respuesta por un fallo puntual de este paso.
    
    NUEVO (2026-08-12): Acepta chunks_by_id opcional para evidence-based
    highlighting. Si el LLM devuelve evidencias, se usan para construir
    sources precisos con texto exacto en vez de item_refs."""
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
        # NUEVO: Si hay evidencias y chunks_by_id, usa evidence-based resolution
        narrative = _resolve_narrative_sources(
            raw_narrative,
            items,
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
        )
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


def _build_chunks_index_from_search(analysis_id: str, correlation_id: str) -> dict[tuple[str, int], list[dict]]:
    """Construye índice de chunks por (document_id, page_number) desde Azure Search.
    
    FIX CRÍTICO (2026-08-12): Necesario para que compute_highlights_for_sources
    pueda buscar los chunks que contienen cada citation y extraer sus bbox.
    
    Args:
        analysis_id: ID del análisis para filtrar chunks
        correlation_id: ID para logging
    
    Returns:
        Diccionario {(document_id, page_number): [chunks en esa página]}
    """
    try:
        from shared.ports.azure_search import search_hybrid
        
        # Obtener todos los chunks del análisis
        # Azure Search vector search limita a 1000 max, así que no pedimos más
        all_chunks = search_hybrid(
            query="*",  # Wildcard = obtener todos los chunks
            analysis_id=analysis_id,
            top_k=1000,  # Máximo soportado por Azure AI Search vector search
            keyword_query=None,
            category_filter=None,
        )
        
        # Construir índice
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
) -> CategoryNarrative:
    """Enriquece una CategoryNarrative con coordenadas de highlight pre-computadas.
    
    FIX CRÍTICO (2026-08): Resuelve el problema de highlight frágil identificado
    en la auditoría RAG. En lugar de usar heurísticas de matching en el frontend,
    pre-computamos las coordenadas exactas usando PyMuPDF con disambiguación
    basada en categoría.
    
    FIX CRÍTICO (2026-08-12): Obtiene chunks desde Azure Search y construye índice
    para que compute_highlights_for_sources pueda filtrar por contenido real.
    
    Args:
        narrative: CategoryNarrative ya construida (output de run_synthesis)
        document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF
        correlation_id: ID para logging
        category_key: Clave de categoría para section_hint (ej: "objeto_alcance")
        analysis_id: ID del análisis (necesario para obtener chunks)
    
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
    
    # FIX CRÍTICO (2026-08-12): Construir índice de chunks desde Azure Search
    chunks_by_doc_page = {}
    if analysis_id:
        chunks_by_doc_page = _build_chunks_index_from_search(analysis_id, correlation_id)
    else:
        logger.warning(
            "highlight_skipped_no_analysis_id",
            correlation_id=correlation_id,
            message="analysis_id no disponible - highlights no se calcularán",
        )
    
    try:
        # Convertir sources a dict para modificar
        sources_data = [source.model_dump() for source in narrative.sources]
        
        # Enriquecer con highlights (ahora CON chunks_by_doc_page)
        enriched_sources_data = compute_highlights_for_sources(
            sources=sources_data,
            document_id_to_blob_path=document_id_to_blob_path,
            correlation_id=correlation_id,
            category_key=category_key,
            chunks_by_doc_page=chunks_by_doc_page,
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
