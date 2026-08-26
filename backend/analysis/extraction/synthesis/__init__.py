"""Sintesis: arma la narrativa final de cada categoria a partir de los items extraidos.

Reexporta lo que el resto del backend importa desde aca: `run_synthesis`,
`enrich_narrative_with_highlights` y `NARRATIVE_CATEGORIES`."""
from analysis.extraction.synthesis.synthesis import (
    CATEGORY_LABELS,
    CATEGORY_OUTPUT_CONTRACTS,
    NARRATIVE_CATEGORIES,
    enrich_narrative_with_highlights,
    run_synthesis,
)

__all__ = [
    "CATEGORY_LABELS",
    "CATEGORY_OUTPUT_CONTRACTS",
    "NARRATIVE_CATEGORIES",
    "enrich_narrative_with_highlights",
    "run_synthesis",
]
