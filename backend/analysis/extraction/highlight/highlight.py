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

import re
from typing import Any

import structlog

from analysis.extraction.highlight.ocr_regions import (
    _renglones_del_chunk,
    pagina_sin_capa_de_texto,
    regiones_desde_renglones_ocr,
)
from analysis.extraction.highlight.search_matching import (
    _normalize_for_search,
    _search_citation_by_words,
    _select_from_occurrences,
    _select_occurrence_rects,
)

logger = structlog.get_logger(__name__)

_CITATION_GAP_MARKER_RE = re.compile(r"\s*(?:\[\.\.\.\]|\u2026)\s*")


def _citation_candidates(citation: str, *, min_length: int) -> list[str]:
    """Variantes de búsqueda para citas no contiguas.

    Algunos sources agrupan múltiples fragmentos del mismo párrafo en un
    único `citation` separado por `[...]`. Ese string NO existe de forma
    contigua en el PDF, así que `search_for` y el fallback por palabras fallan
    aunque la evidencia sea correcta. Esta función mantiene primero la cita
    original y, si detecta marcadores de corte, agrega fragmentos contiguos
    (del más largo al más corto) para intentar ubicar al menos una región.
    """
    normalized = (citation or "").strip()
    if not normalized:
        return []

    candidates: list[str] = [normalized]
    if not _CITATION_GAP_MARKER_RE.search(normalized):
        return candidates

    parts = [part.strip(" .;,:\n\t") for part in _CITATION_GAP_MARKER_RE.split(normalized)]
    parts = [part for part in parts if len(part) >= min_length]
    parts.sort(key=len, reverse=True)
    for part in parts:
        if part not in candidates:
            candidates.append(part)
    return candidates


def _rects_to_regions(rects: list[Any]) -> list[dict[str, float]]:
    """Convierte rectángulos de PyMuPDF al contrato de coordenadas del módulo,
    uniendo en uno solo los fragmentos que caen en el mismo renglón.

    PyMuPDF parte el match por span, así que una cita de 198 caracteres puede
    volver en 24 rectangulitos contiguos. Son correctos, pero el visor tendría
    que dibujar 24 recuadros pegados para representar 3 renglones. Unirlos por
    renglón da la misma superficie con la estructura que el usuario ve.
    """
    if not rects:
        return []

    def _right_edge(rect: Any) -> float:
        x1 = getattr(rect, "x1", None)
        return float(x1) if x1 is not None else float(rect.x0) + float(rect.width)

    lines: list[dict[str, float]] = []
    for rect in rects:
        height = float(rect.height)
        top = float(rect.y0)
        left = float(rect.x0)
        right = _right_edge(rect)

        if lines and abs(top - lines[-1]["y"]) <= max(lines[-1]["height"], 1.0) * 0.3:
            line = lines[-1]
            line["x"] = min(line["x"], left)
            line["_right"] = max(line["_right"], right)
            line["y"] = min(line["y"], top)
            line["height"] = max(line["height"], height)
        else:
            lines.append({"x": left, "y": top, "height": height, "_right": right})

    return [
        {
            "x": line["x"],
            "y": line["y"],
            "width": line["_right"] - line["x"],
            "height": line["height"],
        }
        for line in lines
    ]


def compute_highlight_regions(
    pdf_path: str,
    page_number: int,
    citation: str,
    *,
    correlation_id: str,
    section_hint: str | None = None,
) -> list[dict[str, float]]:
    """Calcula las coordenadas exactas donde aparece una citation en el PDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "highlight_pymupdf_not_installed",
            correlation_id=correlation_id,
            message="PyMuPDF (fitz) no está instalado. Instalar con: pip install PyMuPDF",
        )
        return []
    from infra.config import get_settings

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

        candidates = _citation_candidates(citation, min_length=min_length)
        for candidate_index, candidate in enumerate(candidates):
            if len(candidate.strip()) < min_length:
                continue

            text_instances = page.search_for(candidate)

            if text_instances:
                selected = _select_occurrence_rects(page, text_instances, section_hint, correlation_id)
                regions = _rects_to_regions(selected)
                logger.info(
                    "highlight_found_exact",
                    correlation_id=correlation_id,
                    page_number=page_number,
                    rects_returned_by_search=len(text_instances),
                    regions_count=len(regions),
                    used_citation_candidate=candidate_index,
                    candidate_trimmed=bool(candidate_index > 0),
                )
                return regions

            occurrences = _search_citation_by_words(page, candidate)
            if occurrences:
                selected = _select_from_occurrences(page, occurrences, section_hint, correlation_id)
                regions = _rects_to_regions(selected)
                logger.info(
                    "highlight_found_by_words",
                    correlation_id=correlation_id,
                    page_number=page_number,
                    occurrences=len(occurrences),
                    regions_count=len(regions),
                    reason="search_for no matcheó: la cita cruza una costura del maquetado",
                    used_citation_candidate=candidate_index,
                    candidate_trimmed=bool(candidate_index > 0),
                )
                return regions

        logger.warning(
            "highlight_not_found_in_page",
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


def _resolve_source_chunk(
    source: dict,
    chunks_by_doc_page: dict | None,
    correlation_id: str,
) -> dict | None:
    """El chunk del que salió esta cita, si se lo puede identificar.

    Prioridad al `chunk_id` que anotó `_verify_citation_grounding` (ATR-01):
    adivinar por texto es ambiguo justo donde más duele -- una frase como
    "conforme lo establecido en el presente pliego" aparece en varios chunks de
    la misma página, y el primero que matcheara ganaba.
    """
    if not chunks_by_doc_page:
        return None

    candidates = chunks_by_doc_page.get((source.get("document_id"), source.get("page_number")), [])
    if not candidates:
        return None

    chunk_id = source.get("chunk_id")
    if chunk_id:
        for chunk in candidates:
            if str(chunk.get("id") or chunk.get("chunk_id") or "") == str(chunk_id):
                return chunk
        logger.debug(
            "highlight_chunk_id_not_in_index",
            correlation_id=correlation_id,
            chunk_id=chunk_id,
            fallback="búsqueda por texto entre los chunks de la página",
        )

    citation_normalized = _normalize_for_search(str(source.get("citation", "")))
    if not citation_normalized:
        return None
    for chunk in candidates:
        if citation_normalized in _normalize_for_search(str(chunk.get("content", ""))):
            return chunk
    return None


def compute_highlights_for_sources(
    sources: list[dict[str, Any]],
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
    *,
    category_key: str | None = None,
    chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Enriquece una lista de sources con highlight_regions pre-computadas."""
    enriched_sources = []
    stats = {"total": 0, "with_bbox": 0, "no_bbox": 0}

    for source in sources:
        stats["total"] += 1
        source_copy = dict(source)
        document_id = source.get("document_id")
        page_number = source.get("page_number")
        citation = source.get("citation", "")

        if not document_id or not page_number or not citation:
            source_copy["highlight_regions"] = []
            stats["no_bbox"] += 1
            enriched_sources.append(source_copy)
            continue

        source_chunk = _resolve_source_chunk(source, chunks_by_doc_page, correlation_id)
        section_hint = None
        if source_chunk:
            section_hint = str(source_chunk.get("section_path") or "") or None
            if not section_hint:
                heading_path = source_chunk.get("heading_path") or []
                if isinstance(heading_path, list) and heading_path:
                    section_hint = " ".join(str(part) for part in heading_path)
        if not section_hint and category_key:
            section_hint = category_key.replace("_", " ")

        pdf_path = (document_id_to_blob_path or {}).get(document_id)
        if pdf_path:
            live_regions = compute_highlight_regions(
                pdf_path,
                page_number,
                citation,
                correlation_id=correlation_id,
                section_hint=section_hint,
            )
            if live_regions:
                source_copy["highlight_regions"] = live_regions
                stats["with_bbox"] += 1
                stats["from_live_search"] = stats.get("from_live_search", 0) + 1
                logger.debug(
                    "highlight_from_live_pymupdf_search",
                    correlation_id=correlation_id,
                    document_id=document_id,
                    page_number=page_number,
                    category_key=category_key,
                    regions_count=len(live_regions),
                )
                enriched_sources.append(source_copy)
                continue

        if pdf_path and pagina_sin_capa_de_texto(pdf_path, page_number):
            regiones_ocr = regiones_desde_renglones_ocr(
                _renglones_del_chunk(source_chunk, page_number), citation
            )
            if regiones_ocr:
                source_copy["highlight_regions"] = regiones_ocr
                stats["with_bbox"] += 1
                stats["from_ocr_lines"] = stats.get("from_ocr_lines", 0) + 1
                logger.info(
                    "highlight_from_ocr_lines",
                    correlation_id=correlation_id,
                    document_id=document_id,
                    page_number=page_number,
                    category_key=category_key,
                    regions_count=len(regiones_ocr),
                    message="PDF escaneado: se usó la geometría por renglón de Document Intelligence",
                )
                enriched_sources.append(source_copy)
                continue

            source_copy["highlight_unavailable_reason"] = "documento_escaneado"

        stats["no_bbox"] += 1
        logger.warning(
            "highlight_live_search_found_nothing",
            correlation_id=correlation_id,
            document_id=document_id,
            page_number=page_number,
            category_key=category_key,
            had_pdf=bool(pdf_path),
            section_hint=section_hint,
            citation_preview=citation[:100],
            message="sin regiones: el visor cae al marcado sobre la capa de texto",
        )

        source_copy["highlight_regions"] = []
        enriched_sources.append(source_copy)
    bbox_rate = (stats["with_bbox"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(
        "highlight_enrichment_complete",
        correlation_id=correlation_id,
        category_key=category_key,
        total_sources=stats["total"],
        with_bbox=stats["with_bbox"],
        no_bbox=stats["no_bbox"],
        from_live_search=stats.get("from_live_search", 0),
        from_ocr_lines=stats.get("from_ocr_lines", 0),
        bbox_rate_pct=round(bbox_rate, 1),
    )

    return enriched_sources
