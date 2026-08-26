"""Cálculo de coordenadas de highlight en PDFs.

Reexporta lo que el resto del backend (y los tests) importan desde acá:
`compute_highlight_regions`, `compute_highlights_for_sources` y el resto de
las funciones de matching/OCR que ya se usaban vía `analysis.extraction.highlight`."""
from analysis.extraction.highlight.highlight import (
    _rects_to_regions,
    _resolve_source_chunk,
    compute_highlight_regions,
    compute_highlights_for_sources,
)
from analysis.extraction.highlight.ocr_regions import (
    _renglones_del_chunk,
    _safe_int_page,
    pagina_sin_capa_de_texto,
    regiones_desde_renglones_ocr,
)
from analysis.extraction.highlight.search_matching import (
    _fold,
    _group_rects_by_occurrence,
    _heading_tokens,
    _normalize_for_search,
    _search_citation_by_words,
    _select_best_instance,
    _select_from_occurrences,
    _select_occurrence_rects,
)

__all__ = [
    "compute_highlight_regions",
    "compute_highlights_for_sources",
    "_rects_to_regions",
    "_resolve_source_chunk",
    "pagina_sin_capa_de_texto",
    "regiones_desde_renglones_ocr",
    "_renglones_del_chunk",
    "_safe_int_page",
    "_normalize_for_search",
    "_group_rects_by_occurrence",
    "_heading_tokens",
    "_select_best_instance",
    "_select_occurrence_rects",
    "_select_from_occurrences",
    "_search_citation_by_words",
    "_fold",
]
