from __future__ import annotations

import pytest

from analysis.extraction.schemas import CategoryNarrative
from analysis.extraction.synthesis import (
    SINGLE_PARAGRAPH_CATEGORIES,
    _collapse_to_single_paragraph,
    run_synthesis,
)


def _bullet_narrative() -> CategoryNarrative:
    return CategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "No presentar la garantía de mantenimiento.", "confidence_level": "alta", "source_ids": [0]},
                        {"text": "Presentar la oferta fuera de término.", "confidence_level": "media", "source_ids": [1]},
                    ],
                }
            ],
            "sources": [
                {"id": 0, "document_id": "doc-1", "page_number": 3, "citation": "x"},
                {"id": 1, "document_id": "doc-1", "page_number": 4, "citation": "y"},
            ],
        }
    )


def test_collapse_fusiona_bullet_list_en_un_solo_parrafo() -> None:
    result = _collapse_to_single_paragraph(_bullet_narrative())

    assert len(result.blocks) == 1
    assert result.blocks[0].type == "paragraph"
    assert "No presentar la garantía de mantenimiento." in result.blocks[0].text
    assert "Presentar la oferta fuera de término." in result.blocks[0].text
    # La confianza del párrafo combinado es la más baja de los ítems fusionados.
    assert result.blocks[0].confidence_level == "media"
    assert result.blocks[0].source_ids == [0, 1]


def test_collapse_no_toca_una_narrativa_que_ya_es_un_solo_parrafo() -> None:
    narrative = CategoryNarrative.model_validate(
        {
            "blocks": [{"type": "paragraph", "text": "Ya es un párrafo.", "confidence_level": "alta", "source_ids": [0]}],
            "sources": [],
        }
    )

    result = _collapse_to_single_paragraph(narrative)
    assert result is narrative


def test_run_synthesis_fuerza_un_solo_parrafo_para_causales_rechazo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug real reportado: causales_rechazo (y requisitos_admisibilidad) se
    mostraban como varios ítems sueltos en vez de una sola respuesta. Aunque el
    LLM ignore la instrucción del prompt y devuelva una bullet_list, el
    resultado final tiene que ser un único bloque paragraph."""

    def fake_call_llm(*, messages, correlation_id):
        prompt = messages[0][1]
        assert "UN SOLO bloque de tipo `paragraph`" in prompt
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {"text": "Causal uno.", "confidence_level": "alta", "source_ids": [0]},
                            {"text": "Causal dos.", "confidence_level": "alta", "source_ids": [0]},
                        ],
                    }
                ],
                "sources": [{"id": 0, "document_id": "doc-1", "page_number": 2, "citation": "cita"}],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "causal_rechazo",
            "valor": "Causal uno",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "cita"}],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="causales_rechazo", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "paragraph"


def test_single_paragraph_categories_son_requisitos_y_causales() -> None:
    assert SINGLE_PARAGRAPH_CATEGORIES == {"requisitos_admisibilidad", "causales_rechazo"}
