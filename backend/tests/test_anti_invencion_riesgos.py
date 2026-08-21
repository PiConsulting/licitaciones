"""
Tests para regla anti-invención de riesgos.

Valida que solo se persistan riesgos con evidencia verificable,
descartando hallazgos sin respaldo.
"""

import pytest
from analysis.extraction.graph import _drop_items_without_sources, _enforce_citation_contract


class TestAntiInvencionRiesgos:
    """Tests para regla anti-invención de riesgos."""

    def test_riesgo_sin_fuentes_se_descarta(self):
        """Un riesgo sin source_references debe ser descartado."""
        items = [
            {
                "tipo": "descalificacion",
                "subtipo": "plazos",
                "valor": "Riesgo inventado sin evidencia",
                "source_references": [],  # SIN FUENTES
                "extraction_status": "success",
                "confidence": 0.9,
            }
        ]
        
        filtered, status = _drop_items_without_sources(items, "success", category="riesgos")
        
        assert len(filtered) == 0, "Item sin fuentes debería descartarse"
        assert status == "partial", "Status debería cambiar a partial"

    def test_riesgo_con_fuentes_validas_se_conserva(self):
        """Un riesgo con source_references válidas debe conservarse."""
        items = [
            {
                "tipo": "economico",
                "subtipo": "economico",
                "valor": "Multa por incumplimiento de plazos",
                "source_references": [
                    {
                        "document_id": "doc-123",
                        "page_number": 5,
                        "citation": "Se aplicará multa del 10% por cada día de demora",
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.95,
            }
        ]
        
        filtered, status = _drop_items_without_sources(items, "success", category="riesgos")
        
        assert len(filtered) == 1, "Item con fuentes debe conservarse"
        assert status == "success", "Status debe mantenerse como success"
        assert filtered[0]["valor"] == "Multa por incumplimiento de plazos"

    def test_mezcla_con_y_sin_fuentes(self):
        """Items con fuentes se conservan, sin fuentes se descartan."""
        items = [
            {
                "tipo": "legal",
                "subtipo": "legal_contractual",
                "valor": "Riesgo con evidencia",
                "source_references": [
                    {"document_id": "doc-1", "page_number": 3, "citation": "Evidencia verificable"}
                ],
                "extraction_status": "success",
                "confidence": 0.9,
            },
            {
                "tipo": "operativo",
                "subtipo": "operativo",
                "valor": "Riesgo inventado",
                "source_references": [],  # SIN FUENTES
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "tecnico",
                "subtipo": "tecnico",
                "valor": "Otro riesgo con evidencia",
                "source_references": [
                    {"document_id": "doc-1", "page_number": 7, "citation": "Otra evidencia verificable"}
                ],
                "extraction_status": "success",
                "confidence": 0.85,
            },
        ]
        
        quality = {}
        filtered, status = _drop_items_without_sources(
            items, "success", category="riesgos", quality=quality
        )
        
        assert len(filtered) == 2, "Solo 2 items con fuentes deben conservarse"
        assert status == "partial", "Status debe cambiar a partial por descarte"
        assert quality["riesgos"]["descartados_sin_evidencia"] == 1
        assert quality["riesgos"]["conservados"] == 2

    def test_todos_sin_fuentes_resulta_en_lista_vacia(self):
        """Si todos los items carecen de fuentes, la lista queda vacía."""
        items = [
            {
                "tipo": "otro",
                "subtipo": "otro_explicito",
                "valor": "Riesgo 1 sin evidencia",
                "source_references": [],
                "extraction_status": "success",
                "confidence": 0.7,
            },
            {
                "tipo": "otro",
                "subtipo": "otro_explicito",
                "valor": "Riesgo 2 sin evidencia",
                "source_references": [],
                "extraction_status": "success",
                "confidence": 0.6,
            },
        ]
        
        quality = {}
        filtered, status = _drop_items_without_sources(
            items, "success", category="riesgos", quality=quality
        )
        
        assert len(filtered) == 0, "Todos los items deben descartarse"
        assert status == "partial", "Status debe cambiar a partial"
        assert quality["riesgos"]["descartados_sin_evidencia"] == 2
        assert quality["riesgos"]["conservados"] == 0

    def test_enforce_citation_contract_aplica_a_riesgos(self):
        """_enforce_citation_contract debe limpiar citas inválidas."""
        items = [
            {
                "tipo": "incumplimiento",
                "subtipo": "incumplimiento",
                "valor": "Riesgo con cita corta",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 2,
                        "citation": "Muy corta",  # < 12 caracteres
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.8,
            }
        ]
        
        cleaned = _enforce_citation_contract(items)
        
        # La cita muy corta debería descartarse
        assert len(cleaned[0]["source_references"]) == 0 or len(cleaned[0]["source_references"][0].get("citation", "")) >= 12
