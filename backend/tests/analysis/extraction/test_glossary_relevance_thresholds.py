from __future__ import annotations

from analysis.extraction.glossary import (
    get_category_relevance_min_chunks,
    get_category_relevance_min_ratio,
)


def test_get_category_relevance_min_chunks_usa_override_de_preview_criterios() -> None:
    assert get_category_relevance_min_chunks("preview_criterios") == 14


def test_get_category_relevance_min_chunks_usa_default_si_categoria_no_tiene_override() -> None:
    assert get_category_relevance_min_chunks("garantias", default=10) == 10


def test_get_category_relevance_min_chunks_acepta_string_numerico() -> None:
    assert get_category_relevance_min_chunks("preview_criterios", default=5) == 14


def test_get_category_relevance_min_ratio_usa_override_de_preview_criterios() -> None:
    assert get_category_relevance_min_ratio("preview_criterios") == 0.3


def test_get_category_relevance_min_ratio_usa_default_si_categoria_no_existe() -> None:
    assert get_category_relevance_min_ratio("categoria_inexistente", default=0.4) == 0.4
