"""Conteo de elementos narrativos (bloques/bullets) crudos vs. resueltos, para detectar perdida de contenido en la resolucion de fuentes."""
from __future__ import annotations

import structlog

from analysis.extraction.schemas import CategoryNarrative, RawCategoryNarrative

logger = structlog.get_logger(__name__)


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
