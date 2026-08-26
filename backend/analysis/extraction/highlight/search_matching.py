"""Matching de texto: normalización, selección de instancia y búsqueda por palabras."""
from __future__ import annotations

import re
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
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.split())
    normalized = normalized.lower()
    normalized = normalized.replace("–", "-").replace("—", "-")

    return normalized.strip()


_HEADING_STOPWORDS = {
    "articulo",
    "art",
    "capitulo",
    "seccion",
    "anexo",
    "clausula",
    "punto",
    "inciso",
}


def _heading_tokens(text: str) -> set[str]:
    """Palabras significativas de un encabezado, sin puntuación ni genéricos."""
    normalized = _normalize_for_search(text)
    tokens = {token.strip(".,;:()[]>-") for token in normalized.split()}
    return {token for token in tokens if len(token) >= 2 and token not in _HEADING_STOPWORDS}


def _select_best_instance(
    page: Any,  # fitz.Page
    instances: list[Any],  # list[fitz.Rect]
    section_hint: str,
    correlation_id: str,
) -> list[Any]:
    """Selecciona la instancia más relevante cuando hay múltiples matches."""
    try:
        import fitz

        blocks = page.get_text("dict")["blocks"]

        section_words = _heading_tokens(section_hint)
        relevant_headings = []

        for block in blocks:
            if block.get("type") != 0:  # Solo bloques de texto
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    size = float(span.get("size", 0))
                    bbox = span.get("bbox", None)
                    if size < 11 or not bbox:
                        continue
                    text_words = _heading_tokens(text)
                    common_words = section_words & text_words
                    if common_words:
                        relevant_headings.append(
                            {
                                "text": text,
                                "y": bbox[1],  # top y coordinate
                                "x": bbox[0],  # left x coordinate
                                "common_words": len(common_words),
                            }
                        )

        if not relevant_headings:
            logger.info(
                "highlight_no_relevant_headings_found",
                correlation_id=correlation_id,
                section_hint=section_hint,
                returning_first_instance=True,
            )
            return [min(instances, key=lambda r: r.y0)]
        instance_scores = []
        for instance in instances:
            min_distance = float("inf")
            best_heading = None

            for heading in relevant_headings:
                v_dist = abs(instance.y0 - heading["y"])
                h_dist = abs(instance.x0 - heading["x"])
                distance = (v_dist * 2 + h_dist * 0.5) / (1 + heading["common_words"])

                if distance < min_distance:
                    min_distance = distance
                    best_heading = heading

            instance_scores.append(
                {
                    "instance": instance,
                    "distance": min_distance,
                    "heading": best_heading["text"] if best_heading else None,
                }
            )
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
        return [instances[0]] if instances else []


def _group_rects_by_occurrence(instances: list[Any]) -> list[list[Any]]:
    """Agrupa los rectángulos de `page.search_for()` por APARICIÓN."""
    if not instances:
        return []

    def _right_edge(rect: Any) -> float:
        x1 = getattr(rect, "x1", None)
        if x1 is not None:
            return float(x1)
        return float(rect.x0) + float(rect.width)

    groups: list[list[Any]] = [[instances[0]]]
    for rect in instances[1:]:
        previous = groups[-1][-1]
        line_height = max(float(previous.height), 1.0)
        line_advance = float(rect.y0) - float(previous.y0)

        same_line = abs(line_advance) <= line_height * 0.3
        if same_line:
            horizontal_gap = float(rect.x0) - _right_edge(previous)
            belongs = 0 <= horizontal_gap <= line_height * 1.5
        else:
            belongs = 0 < line_advance <= line_height * 1.8

        if belongs:
            groups[-1].append(rect)
        else:
            groups.append([rect])
    return groups


def _select_occurrence_rects(
    page: Any,
    instances: list[Any],
    section_hint: str | None,
    correlation_id: str,
) -> list[Any]:
    """Elige QUÉ aparición resaltar y devuelve TODOS sus renglones.

    Política única para los dos caminos de `compute_highlight_regions` (búsqueda
    exacta y búsqueda por ancla). Antes el camino por ancla no desambiguaba
    nada y devolvía todos los rectángulos de todas las apariciones -- pintaba
    varios párrafos a la vez, uno solo correcto (hallazgo HL-04). Pintar de más
    es peor que no pintar: parece que el sistema está seguro.
    """
    return _select_from_occurrences(
        page, _group_rects_by_occurrence(instances), section_hint, correlation_id
    )


def _select_from_occurrences(
    page: Any,
    occurrences: list[list[Any]],
    section_hint: str | None,
    correlation_id: str,
) -> list[Any]:
    """Misma política de selección, sobre apariciones YA agrupadas.

    La búsqueda por palabras (`_search_citation_by_words`) conoce los límites de
    cada aparición mientras matchea, así que no necesita reagruparlas por
    geometría -- pero sí necesita la misma política para elegir entre varias.
    """
    if not occurrences:
        return []

    if len(occurrences) == 1:
        return occurrences[0]

    if section_hint:
        first_rects = [occurrence[0] for occurrence in occurrences]
        chosen = _select_best_instance(
            page=page,
            instances=first_rects,
            section_hint=section_hint,
            correlation_id=correlation_id,
        )
        if chosen:
            for occurrence in occurrences:
                if occurrence[0] is chosen[0]:
                    logger.info(
                        "highlight_occurrence_selected",
                        correlation_id=correlation_id,
                        total_occurrences=len(occurrences),
                        selected_lines=len(occurrence),
                        section_hint=section_hint,
                    )
                    return occurrence
    logger.info(
        "highlight_multiple_occurrences_first_kept",
        correlation_id=correlation_id,
        total_occurrences=len(occurrences),
        selected_lines=len(occurrences[0]),
        reason="sin section_hint para desambiguar; resaltar todas confundiría más",
    )
    return occurrences[0]


_ALNUM_RE = re.compile(r"[^a-z0-9]")


def _fold(text: str) -> str:
    """Colapsa un texto a sólo letras y dígitos, sin acentos ni mayúsculas."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _ALNUM_RE.sub("", stripped.lower())


def _search_citation_by_words(page: Any, citation: str) -> list[list[Any]]:
    """Ubica la cita en la página comparando PALABRAS, no la cadena entera."""
    import fitz  # PyMuPDF

    words = page.get_text("words")
    if not words:
        return []

    target = _fold(citation)
    if not target:
        return []
    pieces: list[str] = []
    owner: list[int] = []
    for index, word in enumerate(words):
        folded = _fold(word[4])
        if not folded:
            continue
        pieces.append(folded)
        owner.extend([index] * len(folded))
    haystack = "".join(pieces)
    if not haystack:
        return []

    occurrences: list[list[Any]] = []
    start = haystack.find(target)
    while start >= 0:
        first_word = owner[start]
        last_word = owner[start + len(target) - 1]
        occurrences.append([fitz.Rect(words[i][:4]) for i in range(first_word, last_word + 1)])
        start = haystack.find(target, start + 1)

    return occurrences
