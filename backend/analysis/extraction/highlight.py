"""
Cálculo de coordenadas de highlight en PDFs usando PyMuPDF.

Este módulo resuelve el problema crítico de highlight frágil identificado en la
auditoría RAG: en lugar de usar heurísticas de matching en el frontend, pre-
computamos las coordenadas exactas de cada citation en el PDF usando PyMuPDF
(fitz), que tiene acceso directo a la estructura interna del PDF.

El resultado son coordenadas precisas (x, y, width, height) que el frontend
puede usar para dibujar rectangles de highlight sin falsos positivos/negativos.
"""

from __future__ import annotations

import unicodedata
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _normalize_for_search(text: str) -> str:
    """Normaliza texto para búsqueda tolerante a diferencias de OCR/extracción.
    
    Replica la normalización del backend (_normalize_for_grounding) y la
    extiende para tolerar diferencias comunes de OCR:
    - Elimina acentos (á → a)
    - Normaliza espacios múltiples → espacio simple
    - Lowercase
    - Normaliza guiones (– — → -)
    - Elimina puntuación de fin de oración (opcional, preserva dentro de texto)
    """
    # 1. Normalización Unicode: decompose
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    
    # 2. Eliminar marcas diacríticas (acentos)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    
    # 3. Normalizar espacios (múltiples → simple, tabs/newlines → espacio)
    normalized = " ".join(normalized.split())
    
    # 4. Lowercase
    normalized = normalized.lower()
    
    # 5. Normalizar guiones de diferentes tipos
    normalized = normalized.replace("–", "-").replace("—", "-")
    
    return normalized.strip()


def _select_best_instance(
    page: Any,  # fitz.Page
    instances: list[Any],  # list[fitz.Rect]
    section_hint: str,
    correlation_id: str,
) -> list[Any]:
    """Selecciona la instancia más relevante cuando hay múltiples matches.
    
    FIX DEFINITIVO (2026-08): Resuelve el problema de highlighting cruzado
    entre secciones. Cuando el mismo texto aparece en múltiples lugares de
    la página (ej: "adquisición de insumos" en "Objeto" y en "Requisitos"),
    selecciona la instancia más cercana al título de la sección esperada.
    
    Args:
        page: Página de PyMuPDF
        instances: Lista de rectángulos donde se encontró el texto
        section_hint: Hint de sección (ej: "Objeto y Alcance", "Requisitos")
        correlation_id: ID para logging
    
    Returns:
        Lista con la mejor instancia (o todas si no se puede decidir)
    
    Algoritmo:
        1. Extraer todos los textos en tamaño grande (probables títulos)
        2. Buscar títulos que matcheen con section_hint
        3. Para cada instancia, calcular distancia al título más cercano
        4. Retornar la instancia más cercana a un título relevante
    """
    try:
        import fitz
        
        # Extraer todos los bloques de texto de la página con su posición
        blocks = page.get_text("dict")["blocks"]
        
        # Buscar títulos/headings grandes que contengan palabras del section_hint
        section_words = set(_normalize_for_search(section_hint).split())
        relevant_headings = []
        
        for block in blocks:
            if block.get("type") != 0:  # Solo bloques de texto
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    size = float(span.get("size", 0))
                    bbox = span.get("bbox", None)
                    
                    # Considerar como heading si es texto grande (> 11pt típicamente)
                    if size < 11 or not bbox:
                        continue
                    
                    # Verificar si contiene palabras del section_hint
                    normalized_text = _normalize_for_search(text)
                    text_words = set(normalized_text.split())
                    
                    # Match si comparte al menos 1 palabra significativa
                    common_words = section_words & text_words
                    if common_words:
                        relevant_headings.append({
                            "text": text,
                            "y": bbox[1],  # top y coordinate
                            "x": bbox[0],  # left x coordinate
                            "common_words": len(common_words),
                        })
        
        if not relevant_headings:
            logger.info(
                "highlight_no_relevant_headings_found",
                correlation_id=correlation_id,
                section_hint=section_hint,
                returning_first_instance=True,
            )
            # Sin headings relevantes, retornar primera instancia (más arriba)
            return [min(instances, key=lambda r: r.y0)]
        
        # Calcular distancia de cada instancia al heading más cercano
        instance_scores = []
        for instance in instances:
            # Calcular distancia Manhattan al heading más cercano y relevante
            min_distance = float('inf')
            best_heading = None
            
            for heading in relevant_headings:
                # Distancia vertical (más importante) + distancia horizontal
                v_dist = abs(instance.y0 - heading["y"])
                h_dist = abs(instance.x0 - heading["x"])
                
                # Peso mayor a distancia vertical (secciones están una sobre otra)
                # Bonus por cada palabra común con el section_hint
                distance = (v_dist * 2 + h_dist * 0.5) / (1 + heading["common_words"])
                
                if distance < min_distance:
                    min_distance = distance
                    best_heading = heading
            
            instance_scores.append({
                "instance": instance,
                "distance": min_distance,
                "heading": best_heading["text"] if best_heading else None,
            })
        
        # Seleccionar la instancia con menor distancia
        best = min(instance_scores, key=lambda s: s["distance"])
        
        logger.info(
            "highlight_instance_selected",
            correlation_id=correlation_id,
            section_hint=section_hint,
            selected_near_heading=best["heading"],
            distance=round(best["distance"], 2),
            total_instances=len(instances),
        )
        
        return [best["instance"]]
        
    except Exception as exc:
        logger.warning(
            "highlight_instance_selection_failed",
            correlation_id=correlation_id,
            error=str(exc),
            fallback="returning first instance",
        )
        # Fallback: retornar primera instancia
        return [instances[0]] if instances else []


def _normalize_for_search(text: str) -> str:
    """Normaliza texto para búsqueda tolerante a diferencias de OCR/extracción.
    
    Replica la normalización del backend (_normalize_for_grounding) y la
    extiende para tolerar diferencias comunes de OCR:
    - Elimina acentos (á → a)
    - Normaliza espacios múltiples → espacio simple
    - Lowercase
    - Normaliza guiones (– — → -)
    - Elimina puntuación de fin de oración (opcional, preserva dentro de texto)
    """
    # 1. Normalización Unicode: decompose
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    
    # 2. Eliminar marcas diacríticas (acentos)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    
    # 3. Normalizar espacios (múltiples → simple, tabs/newlines → espacio)
    normalized = " ".join(normalized.split())
    
    # 4. Lowercase
    normalized = normalized.lower()
    
    # 5. Normalizar guiones de diferentes tipos
    normalized = normalized.replace("–", "-").replace("—", "-")
    
    return normalized.strip()


def compute_highlight_regions(
    pdf_path: str,
    page_number: int,
    citation: str,
    *,
    correlation_id: str,
    section_hint: str | None = None,
) -> list[dict[str, float]]:
    """Calcula las coordenadas exactas donde aparece una citation en el PDF.
    
    FIX DEFINITIVO (2026-08): Cuando hay múltiples instancias del mismo texto,
    usa section_hint para seleccionar la instancia correcta basándose en
    proximidad a headings/títulos de la sección.
    
    Args:
        pdf_path: Ruta absoluta al PDF
        page_number: Número de página (1-indexed)
        citation: Texto a buscar (puede venir del chunk original)
        correlation_id: ID para logging
        section_hint: Hint de sección (ej: "Objeto y Alcance") para disambiguación
    
    Returns:
        Lista de rectángulos con coordenadas top-left origin (estándar web):
        [{"x": float, "y": float, "width": float, "height": float}]
        Lista vacía si no se encuentra el texto.
    
    Note:
        Las coordenadas retornadas usan origin top-left (x=0, y=0 en esquina
        superior izquierda), que es el estándar de canvas/SVG web. PyMuPDF
        internamente usa bottom-left, pero esta función ya hace la conversión.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "highlight_pymupdf_not_installed",
            correlation_id=correlation_id,
            message="PyMuPDF (fitz) no está instalado. Instalar con: pip install PyMuPDF",
        )
        return []
    
    # Threshold configurable para longitud mínima de citation
    from shared.config import get_settings
    settings = get_settings()
    min_length = getattr(settings, "highlight_citation_min_length", 3)
    
    if not citation or len(citation.strip()) < min_length:
        logger.warning(
            "highlight_citation_too_short",
            correlation_id=correlation_id,
            citation_length=len(citation.strip()),
            min_length_required=min_length,
        )
        return []
    
    try:
        doc = fitz.open(pdf_path)
        
        if page_number < 1 or page_number > len(doc):
            logger.warning(
                "highlight_invalid_page_number",
                correlation_id=correlation_id,
                page_number=page_number,
                total_pages=len(doc),
            )
            return []
        
        page = doc[page_number - 1]  # PyMuPDF usa 0-indexed
        page_height = page.rect.height  # Para convertir coordenadas
        
        # Estrategia 1: Búsqueda exacta (case-insensitive por defecto en PyMuPDF)
        text_instances = page.search_for(citation)
        
        if text_instances:
            # FIX DEFINITIVO: Si hay múltiples instancias, seleccionar la correcta
            if len(text_instances) > 1 and section_hint:
                text_instances = _select_best_instance(
                    page=page,
                    instances=text_instances,
                    section_hint=section_hint,
                    correlation_id=correlation_id,
                )
                logger.info(
                    "highlight_multiple_instances_disambiguated",
                    correlation_id=correlation_id,
                    page_number=page_number,
                    original_count=len(text_instances),
                    section_hint=section_hint,
                )
            
            # Convertir coordenadas PyMuPDF (bottom-left) a top-left (estándar web)
            regions = [
                {
                    "x": float(rect.x0),
                    "y": float(page_height - rect.y1),  # Conversión a top-left origin
                    "width": float(rect.width),
                    "height": float(rect.height),
                }
                for rect in text_instances
            ]
            logger.info(
                "highlight_found_exact",
                correlation_id=correlation_id,
                page_number=page_number,
                regions_count=len(regions),
            )
            return regions
        
        # Estrategia 2: Búsqueda normalizada (tolerante a diferencias de OCR)
        normalized_citation = _normalize_for_search(citation)
        page_text = page.get_text()
        normalized_page = _normalize_for_search(page_text)
        
        if normalized_citation not in normalized_page:
            logger.warning(
                "highlight_not_found_in_page",
                correlation_id=correlation_id,
                page_number=page_number,
                citation_preview=citation[:50],
            )
            return []
        
        # Si la normalización matchea pero la búsqueda exacta no, intentar
        # buscar fragmentos significativos de la citation
        words = citation.split()
        if len(words) >= 3:
            # Intentar con las primeras 5-10 palabras como ancla
            anchor = " ".join(words[:min(10, len(words))])
            anchor_instances = page.search_for(anchor)
            
            if anchor_instances:
                # Convertir coordenadas a top-left origin
                regions = [
                    {
                        "x": float(rect.x0),
                        "y": float(page_height - rect.y1),
                        "width": float(rect.width),
                        "height": float(rect.height),
                    }
                    for rect in anchor_instances
                ]
                logger.info(
                    "highlight_found_by_anchor",
                    correlation_id=correlation_id,
                    page_number=page_number,
                    anchor_preview=anchor[:50],
                    regions_count=len(regions),
                )
                return regions
        
        logger.warning(
            "highlight_normalization_matched_but_no_coordinates",
            correlation_id=correlation_id,
            page_number=page_number,
            citation_preview=citation[:50],
        )
        return []
        
    except Exception as exc:
        logger.error(
            "highlight_computation_failed",
            correlation_id=correlation_id,
            page_number=page_number,
            error=str(exc),
        )
        return []
    finally:
        if "doc" in locals():
            doc.close()


def compute_highlights_for_sources(
    sources: list[dict[str, Any]],
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
    *,
    category_key: str | None = None,
    chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Enriquece una lista de sources con highlight_regions pre-computadas.
    
    SOLUCIÓN DEFINITIVA V4 (2026-08): Usa campo 'source' estructurado.
    - Migrado de campo legacy 'blocks' a nuevo campo 'source.blocks'
    - Estructura: source.blocks = [{block_id, bbox, text}]
    - Filtra qué block específico contiene la citation
    - Solo agrega bbox del block que matchea (no todos los blocks del chunk)
    - Si no hay source o no matchea, deja highlight_regions vacío
    
    Args:
        sources: Lista de sources (output de synthesis)
        document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF (NO usado)
        correlation_id: ID para logging
        category_key: Clave de categoría (ej: "objeto_alcance") para logs
        chunks_by_doc_page: Índice de chunks por (document_id, page_number) para lookup de source
    
    Returns:
        Lista de sources enriquecidas con campo "highlight_regions"
    """
    enriched_sources = []
    stats = {"total": 0, "with_bbox": 0, "no_bbox": 0, "multiple_blocks": 0}
    
    for source in sources:
        stats["total"] += 1
        source_copy = dict(source)
        document_id = source.get("document_id")
        page_number = source.get("page_number")
        citation = source.get("citation", "")
        
        if not document_id or not page_number or not citation:
            # Source incompleta, conservar sin highlight
            source_copy["highlight_regions"] = []
            stats["no_bbox"] += 1
            enriched_sources.append(source_copy)
            continue
        
        # Buscar chunk que contenga esta citation
        regions = []
        
        if chunks_by_doc_page:
            chunk_key = (document_id, page_number)
            matching_chunks = chunks_by_doc_page.get(chunk_key, [])
            
            # Buscar chunk que contenga esta citation
            for chunk in matching_chunks:
                chunk_content = str(chunk.get("content", ""))
                
                # Match por contenido - citation debe estar en el chunk
                if citation not in chunk_content:
                    continue
                
                # Leer campo 'source' estructurado (nuevo formato RAG)
                source_data = chunk.get("source")
                if not source_data:
                    # Fallback a formato legacy para análisis antiguos
                    source_data = {"blocks": chunk.get("blocks", [])}
                
                blocks = source_data.get("blocks", [])
                
                if not blocks:
                    continue
                
                # FIX V5 (2026-08-11): Detectar si es source agrupada por párrafo
                # Si tiene block_id O la citation contiene "[...]" (múltiples citations combinadas)
                # → resaltar párrafo completo en lugar de filtrar por frase específica
                is_paragraph_grouped = (
                    source.get("block_id") is not None 
                    or "[...]" in citation
                )
                
                if is_paragraph_grouped:
                    # Source agrupada: resaltar TODOS los blocks del párrafo
                    # Si tiene block_id, usar solo el block que matchea ese ID
                    target_block_id = source.get("block_id")
                    
                    for block in blocks:
                        # Si hay block_id, verificar match
                        if target_block_id:
                            block_id = str(block.get("block_id") or block.get("para_id", ""))
                            if block_id != target_block_id:
                                continue
                        
                        # Agregar bbox del block completo (sin filtrar por contenido)
                        bbox = block.get("bbox")
                        if not bbox:
                            continue
                        
                        if isinstance(bbox, dict) and "x" in bbox:
                            regions.append({
                                "x": float(bbox.get("x", 0)),
                                "y": float(bbox.get("y", 0)),
                                "width": float(bbox.get("width", 0)),
                                "height": float(bbox.get("height", 0)),
                            })
                        elif isinstance(bbox, list):
                            for bbox_item in bbox:
                                if bbox_item.get("page") == page_number:
                                    regions.append({
                                        "x": float(bbox_item.get("x", 0)),
                                        "y": float(bbox_item.get("y", 0)),
                                        "width": float(bbox_item.get("width", 0)),
                                        "height": float(bbox_item.get("height", 0)),
                                    })
                    
                    if regions:
                        stats["multiple_blocks"] += 1
                        logger.debug(
                            "highlight_paragraph_grouped",
                            correlation_id=correlation_id,
                            document_id=document_id,
                            page_number=page_number,
                            block_id=target_block_id,
                            category_key=category_key,
                            message="Multiple citations from same paragraph - highlighting entire block"
                        )
                else:
                    # Source única: filtrar block específico que contiene la citation
                    citation_normalized = _normalize_for_search(citation)
                    
                    matched_blocks = []
                    for block in blocks:
                        # Leer texto del block (campo 'text' en nuevo formato, 'content' en legacy)
                        block_text = str(block.get("text") or block.get("content", ""))
                        
                        if not block_text:
                            # Fallback: si no hay texto en el block (análisis antiguos),
                            # agregar el block igual (comportamiento previo)
                            matched_blocks.append(block)
                            continue
                        
                        # Verificar si la citation está en este block específico
                        block_normalized = _normalize_for_search(block_text)
                        if citation_normalized in block_normalized:
                            matched_blocks.append(block)
                    
                    # Extraer bbox solo de los blocks que matchearon
                    for block in matched_blocks:
                        # Nuevo formato: bbox es dict directo {x, y, width, height}
                        # Legacy formato: bbox es lista de dicts con campo 'page'
                        bbox = block.get("bbox")
                        if not bbox:
                            continue
                        
                        # Detectar formato
                        if isinstance(bbox, dict) and "x" in bbox:
                            # Nuevo formato estructurado
                            regions.append({
                                "x": float(bbox.get("x", 0)),
                                "y": float(bbox.get("y", 0)),
                                "width": float(bbox.get("width", 0)),
                                "height": float(bbox.get("height", 0)),
                            })
                        elif isinstance(bbox, list):
                            # Legacy formato: lista de bboxes
                            for bbox_item in bbox:
                                if bbox_item.get("page") == page_number:
                                    regions.append({
                                        "x": float(bbox_item.get("x", 0)),
                                        "y": float(bbox_item.get("y", 0)),
                                        "width": float(bbox_item.get("width", 0)),
                                        "height": float(bbox_item.get("height", 0)),
                                    })
                    
                    if matched_blocks and len(blocks) > 1:
                        stats["multiple_blocks"] += 1
                        logger.debug(
                            "highlight_filtered_blocks",
                            correlation_id=correlation_id,
                            document_id=document_id,
                            page_number=page_number,
                            total_blocks=len(blocks),
                            matched_blocks=len(matched_blocks),
                            category_key=category_key,
                        )
                
                if regions:
                    break  # Encontramos el chunk correcto
        
        if regions:
            stats["with_bbox"] += 1
            logger.debug(
                "highlight_from_azure_di_blocks",
                correlation_id=correlation_id,
                document_id=document_id,
                page_number=page_number,
                category_key=category_key,
                regions_count=len(regions),
            )
        else:
            stats["no_bbox"] += 1
            logger.warning(
                "highlight_no_blocks_available",
                correlation_id=correlation_id,
                document_id=document_id,
                page_number=page_number,
                category_key=category_key,
                citation_preview=citation[:100],
                message="No blocks found for source - highlighting disabled for precision",
            )
        
        source_copy["highlight_regions"] = regions
        enriched_sources.append(source_copy)
    
    # Log stats finales
    bbox_rate = (stats["with_bbox"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(
        "highlight_enrichment_complete",
        correlation_id=correlation_id,
        category_key=category_key,
        total_sources=stats["total"],
        with_bbox=stats["with_bbox"],
        no_bbox=stats["no_bbox"],
        multiple_blocks_filtered=stats["multiple_blocks"],
        bbox_rate_pct=round(bbox_rate, 1),
    )
    
    return enriched_sources
