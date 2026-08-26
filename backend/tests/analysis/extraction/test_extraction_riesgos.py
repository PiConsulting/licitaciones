"""
Tests para la extracción de la categoría Riesgos.

Valida que la categoría Riesgos se integre correctamente en el pipeline
de extracción siguiendo el mismo patrón que las categorías existentes.
"""

import pytest
from analysis.extraction.schemas import ExtractedData, RiesgoItem, SourceReference, TipoRiesgo
from analysis.extraction.extractors import extractor_riesgos


def _source_refs() -> list[SourceReference]:
    return [
        SourceReference(
            document_id="doc-1",
            page_number=1,
            citation="Cita literal del pliego que respalda el riesgo identificado.",
        )
    ]


class TestRiesgosIntegration:
    """Tests de integración para la categoría Riesgos."""

    def test_riesgos_schema_exists(self):
        """La categoría riesgos debe existir en ExtractedData."""
        data = ExtractedData()
        assert hasattr(data, "riesgos")
        assert hasattr(data, "riesgos_extraction_status")
        assert hasattr(data, "riesgos_narrative")
        assert isinstance(data.riesgos, list)
        assert data.riesgos_extraction_status == "unknown"

    def test_riesgos_extractor_exists(self):
        """El extractor de riesgos debe estar disponible."""
        assert callable(extractor_riesgos)


class TestRiesgoItem:
    """Tests para el schema RiesgoItem."""

    def test_riesgo_item_basic_creation(self):
        """Un RiesgoItem se puede crear con campos básicos."""
        item = RiesgoItem(
            tipo=TipoRiesgo.DESCALIFICACION,
            valor="Riesgo de descalificación por documentación incompleta",
            extraction_status="success",
            confidence=0.9,
            source_references=_source_refs(),
        )
        assert item.tipo == TipoRiesgo.DESCALIFICACION
        assert "descalificación" in item.valor
        assert item.extraction_status == "success"

    def test_riesgo_item_all_tipos(self):
        """Todos los tipos de riesgo son válidos."""
        tipos = [
            TipoRiesgo.DESCALIFICACION,
            TipoRiesgo.PENALIZACION,
            TipoRiesgo.LEGAL,
            TipoRiesgo.OPERATIVO,
            TipoRiesgo.FINANCIERO,
            TipoRiesgo.OTRO,
        ]

        for tipo in tipos:
            item = RiesgoItem(
                tipo=tipo,
                valor=f"Riesgo de tipo {tipo.value}",
                extraction_status="success",
                confidence=0.9,
                source_references=_source_refs(),
            )
            assert item.tipo == tipo
