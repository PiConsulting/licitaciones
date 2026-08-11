# Tests para highlight pre-computado

import pytest
from pathlib import Path

from analysis.extraction.highlight import (
    compute_highlight_regions,
    compute_highlights_for_sources,
    _normalize_for_search,
)


def test_normalize_for_search():
    """Normalización debe ser tolerante a diferencias de OCR."""
    # Acentos
    assert _normalize_for_search("garantía del 10%") == _normalize_for_search("garantia del 10%")
    
    # Espacios múltiples
    assert _normalize_for_search("garantía  del   10%") == "garantia del 10%"
    
    # Guiones diferentes
    assert _normalize_for_search("art. 10-15") == _normalize_for_search("art. 10–15")
    assert _normalize_for_search("art. 10—15") == "art. 10-15"
    
    # Case insensitive
    assert _normalize_for_search("GARANTÍA") == _normalize_for_search("garantía")


def test_compute_highlight_regions_citation_too_short():
    """Citations muy cortas no deben procesarse."""
    regions = compute_highlight_regions(
        pdf_path="/fake/path.pdf",
        page_number=1,
        citation="10%",  # Muy corto
        correlation_id="test",
    )
    assert regions == []


def test_compute_highlights_for_sources_missing_pdf():
    """Sources sin PDF path deben conservarse con highlight_regions vacío."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 5,
            "citation": "Esta es una citation de prueba que es suficientemente larga.",
        }
    ]
    
    # Sin mapeo de PDF
    document_id_to_blob_path = {}
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path=document_id_to_blob_path,
        correlation_id="test",
    )
    
    assert len(enriched) == 1
    assert enriched[0]["highlight_regions"] == []


def test_compute_highlights_for_sources_preserves_other_fields():
    """El enriquecimiento debe preservar todos los campos de la source."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 5,
            "citation": "Esta es una citation de prueba.",
            "unverified": True,  # Campo adicional
        }
    ]
    
    document_id_to_blob_path = {}
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path=document_id_to_blob_path,
        correlation_id="test",
    )
    
    assert enriched[0]["id"] == 0
    assert enriched[0]["document_id"] == "doc-1"
    assert enriched[0]["page_number"] == 5
    assert enriched[0]["citation"] == "Esta es una citation de prueba."
    assert enriched[0]["unverified"] is True
    assert "highlight_regions" in enriched[0]


def test_compute_highlights_for_sources_with_new_source_field():
    """Valida que el highlighting funciona con el nuevo campo 'source' estructurado."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Presupuesto oficial de $3.850.000",
        }
    ]
    
    # Simular chunks con el nuevo formato 'source'
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Presupuesto oficial de $3.850.000",
                "source": {
                    "page": 1,
                    "block_type": "table",
                    "blocks": [
                        {
                            "block_id": "para_1",
                            "bbox": {"x": 100.0, "y": 200.0, "width": 300.0, "height": 50.0},
                            "text": "Presupuesto oficial de $3.850.000"
                        }
                    ]
                }
            }
        ]
    }
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )
    
    assert len(enriched) == 1
    assert len(enriched[0]["highlight_regions"]) == 1
    
    region = enriched[0]["highlight_regions"][0]
    assert region["x"] == 100.0
    assert region["y"] == 200.0
    assert region["width"] == 300.0
    assert region["height"] == 50.0


def test_compute_highlights_for_sources_legacy_blocks_format():
    """Valida retrocompatibilidad con el formato legacy 'blocks'."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Garantía del 5%",
        }
    ]
    
    # Simular chunks con formato legacy (blocks directamente en el chunk)
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Garantía del 5%",
                "blocks": [
                    {
                        "page": 1,
                        "content": "Garantía del 5%",
                        "bbox": [
                            {"page": 1, "x": 150.0, "y": 250.0, "width": 200.0, "height": 40.0}
                        ]
                    }
                ]
            }
        ]
    }
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )
    
    assert len(enriched) == 1
    assert len(enriched[0]["highlight_regions"]) == 1
    
    region = enriched[0]["highlight_regions"][0]
    assert region["x"] == 150.0
    assert region["y"] == 250.0


def test_compute_highlights_for_sources_filters_non_matching_blocks():
    """Valida que solo se agregan bboxes de blocks que contienen la citation."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Organismo contratante",
        }
    ]
    
    # Chunk con 3 blocks, solo 1 contiene la citation
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Organismo contratante: Municipalidad\nPresupuesto: $3.850.000\nPlazo: 30 días",
                "source": {
                    "page": 1,
                    "block_type": "table",
                    "blocks": [
                        {
                            "block_id": "para_1",
                            "bbox": {"x": 100.0, "y": 100.0, "width": 300.0, "height": 30.0},
                            "text": "Organismo contratante: Municipalidad"
                        },
                        {
                            "block_id": "para_2",
                            "bbox": {"x": 100.0, "y": 140.0, "width": 300.0, "height": 30.0},
                            "text": "Presupuesto: $3.850.000"
                        },
                        {
                            "block_id": "para_3",
                            "bbox": {"x": 100.0, "y": 180.0, "width": 300.0, "height": 30.0},
                            "text": "Plazo: 30 días"
                        }
                    ]
                }
            }
        ]
    }
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )
    
    # Solo debe haber 1 región (del primer block que contiene "Organismo contratante")
    assert len(enriched) == 1
    assert len(enriched[0]["highlight_regions"]) == 1
    
    region = enriched[0]["highlight_regions"][0]
    assert region["y"] == 100.0  # Primera fila, no las otras


# TODO: Tests de integración con PDF real cuando se tenga un fixture adecuado
# def test_compute_highlight_regions_with_real_pdf():
#     """Test con un PDF fixture que contenga texto conocido."""
#     pdf_path = Path(__file__).parent / "fixtures" / "sample_pliego.pdf"
#     if not pdf_path.exists():
#         pytest.skip("PDF fixture no disponible")
#     
#     regions = compute_highlight_regions(
#         pdf_path=str(pdf_path),
#         page_number=1,
#         citation="Garantía de mantenimiento de oferta",
#         correlation_id="test",
#     )
#     
#     assert len(regions) > 0
#     for region in regions:
#         assert "x" in region
#         assert "y" in region
#         assert "width" in region
#         assert "height" in region
#         assert region["width"] > 0
#         assert region["height"] > 0
