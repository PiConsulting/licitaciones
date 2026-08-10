"""Tests para verificación y deduplicación de citations en síntesis."""
from __future__ import annotations

import pytest

from analysis.extraction.schemas import CategoryNarrative
from analysis.extraction.synthesis import (
    _dedupe_narrative_sources,
    _normalize_text_for_comparison,
    _verify_and_repair_narrative_citations,
)


def test_normalize_text_for_comparison() -> None:
    assert _normalize_text_for_comparison("Hola Mundo") == "hola mundo"
    assert _normalize_text_for_comparison("  múltiples   espacios  ") == "multiples espacios"
    assert _normalize_text_for_comparison("Ñoño") == "nono"
    assert _normalize_text_for_comparison("") == ""


def test_dedupe_narrative_sources_duplicados_exactos() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "Primera cita literal"},
        {"id": 1, "document_id": "doc-1", "page_number": 1, "citation": "Primera cita literal"},
        {"id": 2, "document_id": "doc-1", "page_number": 2, "citation": "Segunda cita"},
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    assert len(deduped) == 2
    assert deduped[0]["citation"] == "Primera cita literal"
    assert deduped[1]["citation"] == "Segunda cita"
    
    # Mapping debe redirigir el ID 1 al 0
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    assert id_mapping[2] == 1


def test_dedupe_narrative_sources_con_variaciones_de_espacios() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "cita   con espacios"},
        {"id": 1, "document_id": "doc-1", "page_number": 1, "citation": "cita con espacios"},
        {"id": 2, "document_id": "doc-1", "page_number": 1, "citation": "cita  con   espacios"},
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    assert len(deduped) == 1
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    assert id_mapping[2] == 0


def test_dedupe_narrative_sources_diferentes_documentos() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "misma cita"},
        {"id": 1, "document_id": "doc-2", "page_number": 1, "citation": "misma cita"},
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Mismo texto pero diferentes documentos = fuentes distintas
    assert len(deduped) == 2
    assert id_mapping[0] == 0
    assert id_mapping[1] == 1


def test_dedupe_narrative_sources_diferentes_paginas() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "misma cita"},
        {"id": 1, "document_id": "doc-1", "page_number": 2, "citation": "misma cita"},
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Mismo texto pero diferentes páginas = fuentes distintas
    assert len(deduped) == 2
    assert id_mapping[0] == 0
    assert id_mapping[1] == 1


def test_verify_and_repair_narrative_citations_marca_no_verificadas(caplog: pytest.LogCaptureFixture) -> None:
    items = [
        {
            "extraction_status": "success",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "Esta es la cita original verificable del pliego",
                }
            ],
        }
    ]
    
    narrative_data = {
        "blocks": [
            {
                "type": "paragraph",
                "text": "Texto del análisis",
                "confidence_level": "alta",
                "source_ids": [0, 1],
            }
        ],
        "sources": [
            {
                "id": 0,
                "document_id": "doc-1",
                "page_number": 1,
                "citation": "Esta es la cita original verificable del pliego",
            },
            {
                "id": 1,
                "document_id": "doc-1",
                "page_number": 1,
                "citation": "Esta cita fue inventada por el LLM y no existe",
            },
        ],
    }
    
    narrative = CategoryNarrative.model_validate(narrative_data)
    result = _verify_and_repair_narrative_citations(
        narrative,
        items,
        correlation_id="test-corr-id",
    )
    
    # La fuente no verificada debe tener marca interna
    sources_dict = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in result.sources]
    verified_source = next((s for s in sources_dict if "verificable" in s.get("citation", "")), None)
    unverified_source = next((s for s in sources_dict if "inventada" in s.get("citation", "")), None)
    
    assert verified_source is not None
    assert "_unverified" not in verified_source
    
    assert unverified_source is not None
    assert unverified_source.get("_unverified") is True
    
    # Debe loggear warning
    assert "narrative_citation_not_grounded" in caplog.text


def test_verify_and_repair_deduplica_y_remapea_ids() -> None:
    items = [
        {
            "extraction_status": "success",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "Cita duplicada en items de entrada",
                }
            ],
        }
    ]
    
    narrative_data = {
        "blocks": [
            {
                "type": "bullet_list",
                "items": [
                    {"text": "Item 1", "confidence_level": "alta", "source_ids": [0]},
                    {"text": "Item 2", "confidence_level": "alta", "source_ids": [1]},
                    {"text": "Item 3", "confidence_level": "alta", "source_ids": [2]},
                ],
            }
        ],
        "sources": [
            {
                "id": 0,
                "document_id": "doc-1",
                "page_number": 1,
                "citation": "Cita duplicada en items de entrada",
            },
            {
                "id": 1,
                "document_id": "doc-1",
                "page_number": 1,
                "citation": "Cita duplicada en items de entrada",
            },
            {
                "id": 2,
                "document_id": "doc-1",
                "page_number": 1,
                "citation": "Cita duplicada en items de entrada",
            },
        ],
    }
    
    narrative = CategoryNarrative.model_validate(narrative_data)
    result = _verify_and_repair_narrative_citations(
        narrative,
        items,
        correlation_id="test-corr-id",
    )
    
    # Debe haber solo 1 source después de deduplicar
    assert len(result.sources) == 1
    
    # Todos los source_ids deben apuntar al mismo ID canónico (0)
    block_data = result.blocks[0].model_dump() if hasattr(result.blocks[0], "model_dump") else dict(result.blocks[0])
    assert all(item["source_ids"] == [0] for item in block_data["items"])


def test_verify_and_repair_preserva_structure_compleja() -> None:
    """Verifica que la función preserve correctamente estructuras complejas
    con bullet_list y table, remapeando source_ids en todos los niveles."""
    items = [
        {
            "extraction_status": "success",
            "source_references": [
                {"document_id": "doc-1", "page_number": 1, "citation": "A" * 30},
            ],
        }
    ]
    
    narrative_data = {
        "blocks": [
            {
                "type": "paragraph",
                "text": "Párrafo",
                "confidence_level": "alta",
                "source_ids": [0],
            },
            {
                "type": "bullet_list",
                "items": [
                    {"text": "Item A", "confidence_level": "alta", "source_ids": [0]},
                    {"text": "Item B", "confidence_level": "alta", "source_ids": [1]},
                ],
            },
            {
                "type": "table",
                "headers": ["Col1", "Col2"],
                "rows": [
                    {"cells": ["a", "b"], "confidence_level": "alta", "source_ids": [0, 1]},
                ],
            },
        ],
        "sources": [
            {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "A" * 30},
            {"id": 1, "document_id": "doc-1", "page_number": 1, "citation": "A" * 30},
        ],
    }
    
    narrative = CategoryNarrative.model_validate(narrative_data)
    result = _verify_and_repair_narrative_citations(
        narrative,
        items,
        correlation_id="test-corr-id",
    )
    
    # Debe deduplicar a 1 source
    assert len(result.sources) == 1
    
    # Verificar remapeo en cada tipo de bloque
    blocks_data = [b.model_dump() if hasattr(b, "model_dump") else dict(b) for b in result.blocks]
    
    # Párrafo
    assert blocks_data[0]["source_ids"] == [0]
    
    # Bullet list items
    assert blocks_data[1]["items"][0]["source_ids"] == [0]
    assert blocks_data[1]["items"][1]["source_ids"] == [0]
    
    # Table rows
    assert blocks_data[2]["rows"][0]["source_ids"] == [0, 0]
