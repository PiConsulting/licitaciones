"""
Tests para regla anti-invención de riesgos.

Valida que solo se persistan riesgos con evidencia verificable,
descartando hallazgos sin respaldo.
"""

import pytest
from analysis.extraction.graph.validation import _drop_items_without_sources, _enforce_citation_contract


class TestAntiInvencionRiesgos:
    """Tests para regla anti-invención de riesgos."""

    def test_riesgo_con_dato_sin_fuentes_se_conserva_flag(self):
        """FIX 2026-09-03: un ítem con `valor` sustantivo pero sin
        `source_references` se conserva (flag, sin botón de fuente) en vez
        de descartarse. Se descartan solo los ítems sin contenido."""
        items = [
            {
                "tipo": "descalificacion",
                "subtipo": "plazos",
                "valor": "Riesgo con dato real cuya cita no se pudo verificar",
                "source_references": [],
                "extraction_status": "success",
                "confidence": 0.9,
            }
        ]

        quality: dict = {}
        filtered, status = _drop_items_without_sources(
            items, "success", category="riesgos", quality=quality
        )

        assert len(filtered) == 1
        assert quality["riesgos"]["conservados_sin_evidencia_verificable"] == 1

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
                "source_references": [],
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "tecnico",
                "subtipo": "tecnico",
                "valor": "Otro riesgo con evidencia",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 7,
                        "citation": "Otra evidencia verificable",
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.85,
            },
        ]

        quality = {}
        filtered, status = _drop_items_without_sources(
            items, "success", category="riesgos", quality=quality
        )

        # El del medio (valor sustantivo, sin fuentes) se conserva flag.
        assert len(filtered) == 3, "Los 3 items se conservan"
        assert quality["riesgos"]["conservados_sin_evidencia_verificable"] == 1
        assert quality["riesgos"]["conservados"] == 3

    def test_todos_con_dato_sin_fuentes_se_conservan_flag(self):
        """FIX 2026-09-03: si todos tienen `valor` sustantivo se conservan
        todos (antes: lista vacía)."""
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

        assert len(filtered) == 2
        assert quality["riesgos"]["conservados_sin_evidencia_verificable"] == 2
        assert quality["riesgos"]["conservados"] == 2

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

        assert (
            len(cleaned[0]["source_references"]) == 0
            or len(cleaned[0]["source_references"][0].get("citation", "")) >= 12
        )
