"""Tests para validar agrupación de sources por párrafo."""

from analysis.extraction.synthesis import _dedupe_narrative_sources


def test_dedupe_same_paragraph_groups_citations():
    """Múltiples citations del mismo párrafo deben agruparse en una source."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Se adquieren insumos de librería",
            "block_id": "para_1"
        },
        {
            "id": 1,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "destinados al municipio",
            "block_id": "para_1"  # Mismo block_id
        },
        {
            "id": 2,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "según especificaciones técnicas",
            "block_id": "para_1"  # Mismo block_id
        },
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Debe haber UNA sola source (agrupadas por block_id)
    assert len(deduped) == 1, f"Expected 1 source, got {len(deduped)}"
    
    # La citation debe combinar las tres
    combined_citation = deduped[0]["citation"]
    assert "Se adquieren insumos de librería" in combined_citation
    assert "[...]" in combined_citation
    assert "destinados al municipio" in combined_citation
    
    # Todos los IDs originales deben mapear al ID canónico
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    assert id_mapping[2] == 0


def test_dedupe_different_paragraphs_separate_sources():
    """Citations de diferentes párrafos deben mantenerse como sources separadas."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Se adquieren insumos de librería",
            "block_id": "para_1"
        },
        {
            "id": 1,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Los oferentes deben presentar certificaciones",
            "block_id": "para_5"  # Diferente block_id
        },
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Debe haber DOS sources (diferentes block_id)
    assert len(deduped) == 2, f"Expected 2 sources, got {len(deduped)}"
    
    # Citations deben estar separadas (sin combinación)
    assert "[...]" not in deduped[0]["citation"]
    assert "[...]" not in deduped[1]["citation"]
    
    # IDs deben mapear a sources diferentes
    assert id_mapping[0] == 0
    assert id_mapping[1] == 1


def test_dedupe_legacy_without_block_id():
    """Sources sin block_id deben usar comportamiento legacy (por citation)."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Se adquieren insumos de librería",
            # Sin block_id
        },
        {
            "id": 1,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Se adquieren insumos de librería",  # Misma citation
            # Sin block_id
        },
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Debe haber UNA source (misma citation)
    assert len(deduped) == 1, f"Expected 1 source, got {len(deduped)}"
    
    # No debe combinar citations (comportamiento legacy)
    assert "[...]" not in deduped[0]["citation"]


def test_dedupe_mixed_same_and_different_paragraphs():
    """Mix de citations: algunas del mismo párrafo, otras de párrafos diferentes."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Objeto: adquisición de insumos",
            "block_id": "para_1"
        },
        {
            "id": 1,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "destinados al municipio",
            "block_id": "para_1"  # Mismo block_id que id=0
        },
        {
            "id": 2,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Requisito: certificación de calidad",
            "block_id": "para_5"  # Diferente block_id
        },
        {
            "id": 3,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "y habilitación comercial",
            "block_id": "para_5"  # Mismo block_id que id=2
        },
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Debe haber DOS sources (para_1 agrupada, para_5 agrupada)
    assert len(deduped) == 2, f"Expected 2 sources, got {len(deduped)}"
    
    # Ambas deben tener citations combinadas
    assert "[...]" in deduped[0]["citation"]
    assert "[...]" in deduped[1]["citation"]
    
    # IDs 0 y 1 → source 0 (para_1)
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    
    # IDs 2 y 3 → source 1 (para_5)
    assert id_mapping[2] == 1
    assert id_mapping[3] == 1


def test_dedupe_preserves_unverified_flag():
    """El flag 'unverified' debe preservarse al agrupar."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Primera cita",
            "block_id": "para_1",
            "unverified": True
        },
        {
            "id": 1,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Segunda cita",
            "block_id": "para_1"  # Mismo block_id
        },
    ]
    
    deduped, id_mapping = _dedupe_narrative_sources(sources)
    
    # Debe haber una source
    assert len(deduped) == 1
    
    # El flag unverified debe preservarse
    assert deduped[0].get("unverified") is True
