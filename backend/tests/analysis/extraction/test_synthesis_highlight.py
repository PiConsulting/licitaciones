"""Tests para validar synthesis y highlight con mejoras implementadas."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from analysis.extraction.synthesis import (
    _empty_category_narrative,
    _resolve_narrative_sources,
    enrich_narrative_with_highlights,
)
from analysis.extraction.highlight import (
    _normalize_for_search,
    compute_highlight_regions,
    compute_highlights_for_sources,
)
from analysis.extraction.schemas import CONFIDENCE_NO_EVIDENCE, CategoryNarrative, RawCategoryNarrative


class TestSynthesisConstant:
    """Tests para verificar uso de constante CONFIDENCE_NO_EVIDENCE."""

    def test_empty_category_narrative_uses_constant(self):
        """_empty_category_narrative usa CONFIDENCE_NO_EVIDENCE en lugar de hardcoded."""
        narrative = _empty_category_narrative("Garantías")
        
        assert len(narrative.blocks) == 1
        assert narrative.blocks[0].type == "paragraph"
        assert narrative.blocks[0].confidence_level == CONFIDENCE_NO_EVIDENCE
        assert narrative.blocks[0].text == "No se encontró información sobre Garantías en los documentos del pliego."
        assert narrative.blocks[0].source_ids == []
        assert narrative.sources == []

    def test_confidence_no_evidence_is_baja(self):
        """CONFIDENCE_NO_EVIDENCE tiene valor 'baja'."""
        assert CONFIDENCE_NO_EVIDENCE == "baja"


class TestResolveNarrativeSources:
    """Tests para verificación estructural de sources."""

    def test_discards_blocks_without_valid_item_refs(self):
        """Bloques con item_refs inválidos son descartados."""
        raw = RawCategoryNarrative.model_validate({
            "blocks": [{
                "type": "paragraph",
                "text": "Texto sin fuente",
                "confidence_level": "alta",
                "item_refs": [999],  # Index fuera de rango
            }]
        })
        items = [{"source_references": [{"document_id": "doc-1", "page_number": 1, "citation": "texto válido"}]}]
        
        narrative = _resolve_narrative_sources(raw, items, correlation_id="test-123")
        
        # Bloque descartado por item_ref inválido
        assert len(narrative.blocks) == 0
        assert len(narrative.sources) == 0

    def test_resolves_valid_item_refs_to_sources(self):
        """item_refs válidos se resuelven a source_ids correctos."""
        raw = RawCategoryNarrative.model_validate({
            "blocks": [{
                "type": "paragraph",
                "text": "Texto con fuente",
                "confidence_level": "alta",
                "item_refs": [0],
            }]
        })
        items = [{
            "source_references": [{
                "document_id": "doc-1",
                "page_number": 5,
                "citation": "Los oferentes deberán presentar garantía...",
            }]
        }]
        
        narrative = _resolve_narrative_sources(raw, items, correlation_id="test-123")
        
        assert len(narrative.blocks) == 1
        assert narrative.blocks[0].source_ids == [0]
        assert len(narrative.sources) == 1
        assert narrative.sources[0].document_id == "doc-1"
        assert narrative.sources[0].page_number == 5
        assert narrative.sources[0].id == 0

    def test_deduplicates_sources_with_same_citation(self):
        """Sources con mismo doc + page + citation normalizada se dedupl ican."""
        raw = RawCategoryNarrative.model_validate({
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Item 1", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Item 2", "confidence_level": "alta", "item_refs": [1]},
                    ],
                }
            ]
        })
        # Dos items con misma source (doc + page + citation)
        items = [
            {
                "source_references": [{
                    "document_id": "doc-1",
                    "page_number": 5,
                    "citation": "Los oferentes deberán presentar garantía de mantenimiento...",
                }]
            },
            {
                "source_references": [{
                    "document_id": "doc-1",
                    "page_number": 5,
                    "citation": "Los oferentes deberán presentar garantía de mantenimiento...",  # Misma citation
                }]
            },
        ]
        
        narrative = _resolve_narrative_sources(raw, items, correlation_id="test-123")
        
        # Dos bullets, pero solo 1 source (deduplicada)
        assert len(narrative.blocks) == 1
        assert len(narrative.blocks[0].items) == 2
        assert len(narrative.sources) == 1  # Deduplicada
        # Ambos bullets apuntan al mismo source_id
        assert narrative.blocks[0].items[0].source_ids == [0]
        assert narrative.blocks[0].items[1].source_ids == [0]


class TestHighlightNormalization:
    """Tests para normalización de texto en búsqueda."""

    def test_normalize_removes_accents(self):
        """_normalize_for_search elimina acentos."""
        text = "Garantía de mantenimiento para adquisición"
        normalized = _normalize_for_search(text)
        
        assert "á" not in normalized
        assert "é" not in normalized
        assert "í" not in normalized
        assert "garantia" in normalized
        assert "adquisicion" in normalized

    def test_normalize_lowercase(self):
        """_normalize_for_search convierte a lowercase."""
        text = "GARANTÍA DE MANTENIMIENTO"
        normalized = _normalize_for_search(text)
        
        assert normalized == "garantia de mantenimiento"

    def test_normalize_multiple_spaces(self):
        """_normalize_for_search colapsa espacios múltiples."""
        text = "Garantía    de     mantenimiento"
        normalized = _normalize_for_search(text)
        
        assert normalized == "garantia de mantenimiento"

    def test_normalize_hyphens(self):
        """_normalize_for_search normaliza diferentes tipos de guiones."""
        text = "Garantía–de—mantenimiento-de-oferta"
        normalized = _normalize_for_search(text)
        
        assert normalized == "garantia-de-mantenimiento-de-oferta"


class TestHighlightCoordinateConversion:
    """Tests para conversión de coordenadas PyMuPDF a top-left origin."""

    @patch("analysis.extraction.highlight.fitz")
    def test_compute_highlight_converts_to_top_left(self, mock_fitz):
        """compute_highlight_regions convierte coordenadas a top-left origin."""
        # Mock PyMuPDF
        mock_doc = Mock()
        mock_page = Mock()
        mock_rect = Mock()
        mock_rect.x0 = 72.0
        mock_rect.y0 = 450.0  # Bottom-left y
        mock_rect.y1 = 486.0  # Bottom-left y + height
        mock_rect.width = 420.0
        mock_rect.height = 36.0
        
        mock_page.rect.height = 800.0  # Page height
        mock_page.search_for.return_value = [mock_rect]
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__len__.return_value = 20
        mock_fitz.open.return_value = mock_doc
        
        regions = compute_highlight_regions(
            pdf_path="/tmp/test.pdf",
            page_number=1,
            citation="Test citation",
            correlation_id="test-123",
        )
        
        assert len(regions) == 1
        # Verificar conversión: y_topleft = page_height - y_bottomleft - height
        # y_topleft = 800 - 486 = 314
        assert regions[0]["x"] == 72.0
        assert regions[0]["y"] == 314.0  # Convertido a top-left
        assert regions[0]["width"] == 420.0
        assert regions[0]["height"] == 36.0

    @patch("analysis.extraction.highlight.fitz")
    def test_compute_highlight_multiple_regions(self, mock_fitz):
        """Múltiples matches producen múltiples regiones convertidas."""
        mock_doc = Mock()
        mock_page = Mock()
        
        # Dos rects encontrados
        mock_rect1 = Mock(x0=72.0, y0=450.0, y1=486.0, width=420.0, height=36.0)
        mock_rect2 = Mock(x0=72.0, y0=600.0, y1=636.0, width=420.0, height=36.0)
        
        mock_page.rect.height = 800.0
        mock_page.search_for.return_value = [mock_rect1, mock_rect2]
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__len__.return_value = 20
        mock_fitz.open.return_value = mock_doc
        
        regions = compute_highlight_regions(
            pdf_path="/tmp/test.pdf",
            page_number=1,
            citation="Test citation",
            correlation_id="test-123",
        )
        
        assert len(regions) == 2
        # Primera región: y = 800 - 486 = 314
        assert regions[0]["y"] == 314.0
        # Segunda región: y = 800 - 636 = 164
        assert regions[1]["y"] == 164.0


class TestHighlightConfigurableThreshold:
    """Tests para threshold configurable de citation."""

    @patch("analysis.extraction.highlight.fitz")
    @patch("analysis.extraction.highlight.get_settings")
    def test_uses_configurable_min_length(self, mock_settings, mock_fitz):
        """compute_highlight_regions usa highlight_citation_min_length de config."""
        mock_settings_instance = Mock()
        mock_settings_instance.highlight_citation_min_length = 10  # Custom threshold
        mock_settings.return_value = mock_settings_instance
        
        # Citation de 5 caracteres (menos que threshold)
        regions = compute_highlight_regions(
            pdf_path="/tmp/test.pdf",
            page_number=1,
            citation="short",  # 5 chars < 10
            correlation_id="test-123",
        )
        
        # Debe retornar vacío por citation too short
        assert regions == []

    @patch("analysis.extraction.highlight.fitz")
    @patch("analysis.extraction.highlight.get_settings")
    def test_default_min_length_is_3(self, mock_settings, mock_fitz):
        """Si config no tiene highlight_citation_min_length, usa default 3."""
        mock_settings_instance = Mock(spec=[])  # Sin el atributo
        mock_settings.return_value = mock_settings_instance
        
        mock_doc = Mock()
        mock_page = Mock()
        mock_page.rect.height = 800.0
        mock_page.search_for.return_value = []
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__len__.return_value = 20
        mock_fitz.open.return_value = mock_doc
        
        # Citation de 4 caracteres (>= default 3)
        regions = compute_highlight_regions(
            pdf_path="/tmp/test.pdf",
            page_number=1,
            citation="test",  # 4 chars >= 3 (default)
            correlation_id="test-123",
        )
        
        # No debe fallar por citation too short (>= default threshold)
        # Retorna [] porque no hay matches, no por threshold
        assert regions == []


class TestEnrichNarrativeWithHighlights:
    """Tests de integración para enriquecimiento con highlights."""

    @patch("analysis.extraction.synthesis.compute_highlights_for_sources")
    def test_enriches_sources_with_highlights(self, mock_compute):
        """enrich_narrative_with_highlights agrega highlight_regions a sources."""
        narrative = CategoryNarrative.model_validate({
            "blocks": [{
                "type": "paragraph",
                "text": "Texto con fuente",
                "confidence_level": "alta",
                "source_ids": [0],
            }],
            "sources": [{
                "id": 0,
                "document_id": "doc-1",
                "page_number": 5,
                "citation": "Los oferentes deberán...",
            }],
        })
        
        # Mock compute_highlights_for_sources retorna sources enriquecidas
        mock_compute.return_value = [{
            "id": 0,
            "document_id": "doc-1",
            "page_number": 5,
            "citation": "Los oferentes deberán...",
            "highlight_regions": [{
                "x": 72.0,
                "y": 314.0,
                "width": 420.0,
                "height": 36.0,
            }],
        }]
        
        document_mapping = {"doc-1": "/tmp/doc-1.pdf"}
        
        enriched = enrich_narrative_with_highlights(
            narrative=narrative,
            document_id_to_blob_path=document_mapping,
            correlation_id="test-123",
        )
        
        # Verificar que sources fueron enriquecidas
        assert len(enriched.sources) == 1
        assert len(enriched.sources[0].highlight_regions) == 1
        assert enriched.sources[0].highlight_regions[0]["x"] == 72.0
        assert enriched.sources[0].highlight_regions[0]["y"] == 314.0

    @patch("analysis.extraction.synthesis.HIGHLIGHT_AVAILABLE", False)
    def test_returns_unchanged_if_highlight_not_available(self):
        """Si PyMuPDF no disponible, retorna narrative sin modificar."""
        narrative = CategoryNarrative.model_validate({
            "blocks": [{
                "type": "paragraph",
                "text": "Texto",
                "confidence_level": "alta",
                "source_ids": [0],
            }],
            "sources": [{
                "id": 0,
                "document_id": "doc-1",
                "page_number": 5,
                "citation": "Text",
            }],
        })
        
        document_mapping = {"doc-1": "/tmp/doc-1.pdf"}
        
        enriched = enrich_narrative_with_highlights(
            narrative=narrative,
            document_id_to_blob_path=document_mapping,
            correlation_id="test-123",
        )
        
        # Debe retornar narrative original sin highlight_regions
        assert enriched == narrative


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Garantía de mantenimiento", "garantia de mantenimiento"),
        ("ADQUISICIÓN DE BIENES", "adquisicion de bienes"),
        ("pingü-ino", "pingu-ino"),
        ("texto    con     espacios", "texto con espacios"),
        ("guión–largo—em-dash", "guion-largo-em-dash"),
    ],
)
def test_normalize_parametrized(text: str, expected: str):
    """Tests parametrizados para normalización."""
    assert _normalize_for_search(text) == expected
