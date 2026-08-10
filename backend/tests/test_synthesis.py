from __future__ import annotations

import pytest

from analysis.extraction.synthesis import run_synthesis


def test_response_base_prompt_no_fuerza_formato_por_categoria() -> None:
    """El formato (parrafo/lista/tabla) lo decide el LLM segun el contenido de
    CADA pliego, no una regla dura por categoria (ver Fase 5 del rediseno del
    pipeline: se elimino SINGLE_PARAGRAPH_CATEGORIES/CHECKLIST_CATEGORIES)."""
    from analysis.extraction.synthesis import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "{checklist_hint}" not in prompt
    assert "Elegís el formato según el contenido" in prompt


def test_run_synthesis_respeta_el_formato_que_devuelve_el_llm_bullet_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {"text": "Presentar certificado fiscal.", "confidence_level": "alta", "source_ids": [0]},
                            {"text": "Acreditar capacidad técnica mínima.", "confidence_level": "alta", "source_ids": [0]},
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
            "tipo": "documento",
            "valor": "Certificado fiscal",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "cita"}],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="requisitos_admisibilidad", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "bullet_list"
    assert len(narrative.blocks[0].items) == 2


def test_run_synthesis_respeta_el_formato_que_devuelve_el_llm_paragraph(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Serán causales de rechazo la falta de garantía y la presentación fuera de término.",
                        "confidence_level": "alta",
                        "source_ids": [0],
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


def test_response_base_prompt_incluye_regla_de_formato_de_fecha() -> None:
    from analysis.extraction.synthesis import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "Fechas y horas en formato natural" in prompt
    assert "formato argentino" in prompt


def test_response_base_prompt_prioriza_checklist_breve() -> None:
    from analysis.extraction.synthesis import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "Modo checklist breve" in prompt
    assert "items de una sola idea" in prompt


def test_run_synthesis_convierte_fecha_iso_a_formato_natural(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call_llm(*, messages, correlation_id):
        prompt = messages[0][1]
        assert "Fechas y horas en formato natural" in prompt
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "La oferta debe presentarse antes del 15 de septiembre de 2026 a las 14:30 hs.",
                        "confidence_level": "alta",
                        "source_ids": [0],
                    }
                ],
                "sources": [{"id": 0, "document_id": "doc-1", "page_number": 4, "citation": "cita"}],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "presentación ofertas",
            "fecha": "2026-09-15",
            "hora": "14:30",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 4, "citation": "cita"}],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="plazos_clave", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert "15 de septiembre de 2026" in narrative.blocks[0].text
    assert "2026-09-15" not in narrative.blocks[0].text
