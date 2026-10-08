"""Tests para `get_category_penalty` (glossary.py).

FIX (2026-09-03, Fase 1.4 del plan RAG): category_penalty configurable por
categoría, mismo patrón que `get_category_top_k`. El dataset de evaluación
(evaluation/datasets/retrieval_eval_v1.json) mostró que el penalty default
de -30% perjudica el recall de `preview_criterios` en chunks con contenido
multi-categoría; se agregó un override puntual en glossary.json en vez de
bajar el default global (que afectaría a las otras 9 categorías sin
evidencia). Ver docs/docu/PLAN-fix-preview-criterios-y-hardcodeo-rag.md,
sección 1.4.
"""

from __future__ import annotations

from analysis.extraction.glossary import get_category_penalty


def test_get_category_penalty_usa_override_de_preview_criterios() -> None:
    """glossary.json define category_penalty=0.0 para preview_criterios
    (evidencia empírica en el plan: el penalty default perjudica el recall
    de esta categoría en chunks con contenido multi-categoría)."""
    assert get_category_penalty("preview_criterios") == 0.0


def test_get_category_penalty_usa_default_si_la_categoria_no_tiene_override() -> None:
    """Categorías sin `category_penalty` en su entrada de glossary.json
    (todavía sin evidencia que justifique bajarlo) siguen usando el default
    de producción de `_retrieve_with_category_priority` (0.30)."""
    # Estas categorías no tienen override en glossary.json (a diferencia de otras, desde el experimento penalty=0.15 de 2026-09-09).
    assert get_category_penalty("garantias", default=0.30) == 0.30
    assert get_category_penalty("requisitos_admisibilidad", default=0.30) == 0.30


def test_get_category_penalty_usa_default_si_la_categoria_no_existe() -> None:
    assert get_category_penalty("categoria_inexistente", default=0.30) == 0.30


def test_get_category_penalty_acepta_int_y_string_numerico() -> None:
    # Ninguna categoría real usa estos formatos hoy, pero debe tolerarlos igual que get_category_top_k tolera top_k como string.
    from analysis.extraction import glossary as glossary_module

    original_load = glossary_module._load_glossary
    try:
        glossary_module._load_glossary.cache_clear()
        glossary_module._load_glossary = lambda: {  # type: ignore[assignment]
            "cat_int": {"category_penalty": 0},
            "cat_str": {"category_penalty": "0.15"},
            "cat_bool": {"category_penalty": True},
            "cat_invalid": {"category_penalty": "no-es-un-numero"},
        }
        assert get_category_penalty("cat_int", default=0.30) == 0.0
        assert get_category_penalty("cat_str", default=0.30) == 0.15
        # bool es subclase de int en Python -- se descarta para no interpretar True/False como 1.0/0.0.
        assert get_category_penalty("cat_bool", default=0.30) == 0.30
        assert get_category_penalty("cat_invalid", default=0.30) == 0.30
    finally:
        glossary_module._load_glossary = original_load
        glossary_module._load_glossary.cache_clear()
