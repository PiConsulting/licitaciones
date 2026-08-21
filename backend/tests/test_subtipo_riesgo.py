"""
Tests para la clasificación de subtipos de riesgo.

Valida que los riesgos se clasifican correctamente en subtipos
para facilitar la priorización de mitigación.
"""

import pytest
from analysis.extraction.schemas import RiesgoItem, SubtipoRiesgo, SourceReference


class TestSubtipoRiesgo:
    """Tests para el enum SubtipoRiesgo."""

    def test_subtipo_riesgo_enum_exists(self):
        """El enum SubtipoRiesgo debe existir con todos los subtipos."""
        assert hasattr(SubtipoRiesgo, 'EJECUCION')
        assert hasattr(SubtipoRiesgo, 'INCUMPLIMIENTO')
        assert hasattr(SubtipoRiesgo, 'OPERATIVO')
        assert hasattr(SubtipoRiesgo, 'PLAZOS')
        assert hasattr(SubtipoRiesgo, 'ECONOMICO')
        assert hasattr(SubtipoRiesgo, 'TECNICO')
        assert hasattr(SubtipoRiesgo, 'LEGAL_CONTRACTUAL')
        assert hasattr(SubtipoRiesgo, 'OTRO_EXPLICITO')

    def test_subtipo_values(self):
        """Los valores del enum deben ser correctos."""
        assert SubtipoRiesgo.EJECUCION.value == "ejecucion"
        assert SubtipoRiesgo.INCUMPLIMIENTO.value == "incumplimiento"
        assert SubtipoRiesgo.OPERATIVO.value == "operativo"
        assert SubtipoRiesgo.PLAZOS.value == "plazos"
        assert SubtipoRiesgo.ECONOMICO.value == "economico"
        assert SubtipoRiesgo.TECNICO.value == "tecnico"
        assert SubtipoRiesgo.LEGAL_CONTRACTUAL.value == "legal_contractual"
        assert SubtipoRiesgo.OTRO_EXPLICITO.value == "otro_explicito"


class TestRiesgoItemWithSubtipo:
    """Tests para RiesgoItem con campo subtipo."""

    def test_riesgo_item_has_subtipo_field(self):
        """RiesgoItem debe tener un campo subtipo."""
        source_ref = SourceReference(
            document_id="test-doc-123",
            page_number=5,
            citation="Riesgo de incumplimiento de plazo según cláusula 15"
        )
        item = RiesgoItem(
            tipo="descalificacion",
            subtipo=SubtipoRiesgo.PLAZOS,
            valor="Riesgo de incumplimiento de plazo de entrega",
            confidence=0.9,
            extraction_status="success",
            source_references=[source_ref],
        )
        assert item.subtipo == SubtipoRiesgo.PLAZOS
        assert item.subtipo.value == "plazos"

    def test_all_subtipos_work(self):
        """Todos los subtipos deben ser válidos en RiesgoItem."""
        source_ref = SourceReference(
            document_id="test-doc",
            page_number=1,
            citation="Riesgo de prueba según artículo X"
        )
        
        for subtipo in SubtipoRiesgo:
            item = RiesgoItem(
                tipo="otro",
                subtipo=subtipo,
                valor=f"Riesgo de subtipo {subtipo.value}",
                confidence=0.8,
                extraction_status="success",
                source_references=[source_ref],
            )
            assert item.subtipo == subtipo

    def test_riesgo_ambiguo_usa_otro_explicito(self):
        """Un riesgo ambiguo debe quedar en otro_explicito sin perder evidencia."""
        source_ref = SourceReference(
            document_id="test-doc",
            page_number=10,
            citation="Situación de riesgo no especificada en el artículo 42"
        )
        
        item = RiesgoItem(
            tipo="otro",
            subtipo=SubtipoRiesgo.OTRO_EXPLICITO,
            valor="Riesgo no clasificable en categorías específicas",
            confidence=0.7,
            extraction_status="success",
            source_references=[source_ref],
        )
        
        assert item.subtipo == SubtipoRiesgo.OTRO_EXPLICITO
        assert len(item.source_references) == 1
        assert item.source_references[0].citation == "Situación de riesgo no especificada en el artículo 42"
