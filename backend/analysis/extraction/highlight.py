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


def compute_highlight_regions(
    pdf_path: str,
    page_number: int,
    citation: str,
    *,
    correlation_id: str,
) -> list[dict[str, float]]:
    """Calcula las coordenadas exactas donde aparece una citation en el PDF.
    
    Args:
        pdf_path: Ruta absoluta al PDF
        page_number: Número de página (1-indexed)
        citation: Texto a buscar (puede venir del chunk original)
        correlation_id: ID para logging
    
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
) -> list[dict[str, Any]]:
    """Enriquece una lista de sources con highlight_regions pre-computadas.
    
    Args:
        sources: Lista de sources (output de synthesis)
        document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF
        correlation_id: ID para logging
    
    Returns:
        Lista de sources enriquecidas con campo "highlight_regions"
    """
    enriched_sources = []
    
    for source in sources:
        source_copy = dict(source)
        document_id = source.get("document_id")
        page_number = source.get("page_number")
        citation = source.get("citation", "")
        
        if not document_id or not page_number or not citation:
            # Source incompleta, conservar sin highlight
            source_copy["highlight_regions"] = []
            enriched_sources.append(source_copy)
            continue
        
        pdf_path = document_id_to_blob_path.get(document_id)
        if not pdf_path:
            logger.warning(
                "highlight_pdf_path_not_found",
                correlation_id=correlation_id,
                document_id=document_id,
            )
            source_copy["highlight_regions"] = []
            enriched_sources.append(source_copy)
            continue
        
        regions = compute_highlight_regions(
            pdf_path=pdf_path,
            page_number=page_number,
            citation=citation,
            correlation_id=correlation_id,
        )
        
        source_copy["highlight_regions"] = regions
        enriched_sources.append(source_copy)
    
    return enriched_sources
