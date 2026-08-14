"""Tests for split heading merger across pages."""

from extraction.chunking import _merge_split_headings_across_pages


def test_merge_split_heading_across_pages():
    """Verifica que headings partidos entre páginas se fusionen correctamente."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 12: PLA",
            "page_number": 4,
            "source_order": 1,
        },
        {
            "heading_level": 2,
            "content": "ZO DE ENTREGA",
            "page_number": 5,
            "source_order": 1,
        },
        {
            "block_type": "paragraph",
            "content": "El plazo de entrega será...",
            "page_number": 5,
            "source_order": 2,
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    # Debe fusionar los dos primeros bloques
    assert len(result) == 2
    assert result[0]["content"] == "ARTÍCULO 12: PLAZO DE ENTREGA"
    assert result[0]["page_number"] == 4  # Mantiene página del primero
    assert result[1]["content"] == "El plazo de entrega será..."


def test_merge_split_heading_lowercase_continuation():
    """Verifica fusión cuando siguiente bloque empieza con minúscula."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 6: DOCUMEN",
            "page_number": 2,
            "source_order": 1,
        },
        {
            "heading_level": 2,
            "content": "tación a Presentar",
            "page_number": 3,
            "source_order": 1,
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    assert len(result) == 1
    assert result[0]["content"] == "ARTÍCULO 6: DOCUMENtación a Presentar"


def test_no_merge_for_complete_headings():
    """No fusiona headings completos que están en páginas consecutivas."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 10: GARANTÍAS",
            "page_number": 3,
            "source_order": 1,
        },
        {
            "heading_level": 2,
            "content": "ARTÍCULO 11: PLAZOS DE ENTREGA",
            "page_number": 4,
            "source_order": 1,
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    # No debe fusionar (ambos headings completos)
    assert len(result) == 2
    assert result[0]["content"] == "ARTÍCULO 10: GARANTÍAS"
    assert result[1]["content"] == "ARTÍCULO 11: PLAZOS DE ENTREGA"


def test_no_merge_different_levels():
    """No fusiona headings de niveles diferentes."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 12: PLA",
            "page_number": 4,
            "source_order": 1,
        },
        {
            "heading_level": 3,
            "content": "ZO DE ENTREGA",
            "page_number": 5,
            "source_order": 1,
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    # No debe fusionar (niveles diferentes)
    assert len(result) == 2


def test_no_merge_non_consecutive_pages():
    """No fusiona headings que no están en páginas consecutivas."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 12: PLA",
            "page_number": 4,
            "source_order": 1,
        },
        {
            "heading_level": 2,
            "content": "ZO DE ENTREGA",
            "page_number": 6,  # Salto de página
            "source_order": 1,
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    # No debe fusionar (no consecutivas)
    assert len(result) == 2


def test_merge_preserves_metadata():
    """Verifica que la fusión preserve metadata del primer bloque."""
    blocks = [
        {
            "heading_level": 2,
            "content": "ARTÍCULO 12: PLA",
            "page_number": 4,
            "source_order": 1,
            "para_id": [4, 1],
            "bbox": [100, 200, 300, 50],
        },
        {
            "heading_level": 2,
            "content": "ZO DE ENTREGA",
            "page_number": 5,
            "source_order": 1,
            "para_id": [5, 1],
            "bbox": [100, 50, 300, 50],
        },
    ]
    
    result = _merge_split_headings_across_pages(blocks)
    
    assert len(result) == 1
    merged = result[0]
    assert merged["content"] == "ARTÍCULO 12: PLAZO DE ENTREGA"
    assert merged["page_number"] == 4  # Del primero
    assert merged["para_id"] == [4, 1]  # Del primero
    assert merged["bbox"] == [100, 200, 300, 50]  # Del primero
