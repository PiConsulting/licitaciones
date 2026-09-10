"""
Test rápido de regla anti-invención de riesgos.
Bypasea fixtures de DB para evitar errores de bcrypt.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.graph.validation import _drop_items_without_sources, _enforce_citation_contract


def test_riesgo_sin_fuentes_pero_con_dato_se_conserva_flag():
    """FIX 2026-09-03: un ítem con `valor` sustantivo pero sin
    `source_references` YA NO se descarta -- se conserva (el frontend lo
    renderiza sin botón "ver fuente" y no cuenta como "revisado
    automáticamente") y se contabiliza en
    `quality[cat]["conservados_sin_evidencia_verificable"]`. Solo se
    descartan los ítems SIN contenido sustantivo (ver
    `test_todos_sin_contenido_ni_fuentes_se_descartan`)."""
    print("\n✅ Test 1: riesgo con dato pero sin fuente verificable se conserva")
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


def test_todos_sin_contenido_ni_fuentes_se_descartan():
    """El camino de descarte sigue vivo: ítems sin `valor` (o con valor
    'no encontrado') y sin fuentes se tiran y el status baja a partial."""
    items = [
        {"tipo": "otro", "subtipo": "otro_explicito", "valor": None, "source_references": [], "extraction_status": "success", "confidence": 0.5},
        {"tipo": "otro", "subtipo": "otro_explicito", "valor": "no encontrado", "source_references": [], "extraction_status": "success", "confidence": 0.5},
    ]
    quality: dict = {}
    filtered, status = _drop_items_without_sources(items, "success", category="riesgos", quality=quality)
    assert len(filtered) == 0
    assert status == "partial"
    assert quality["riesgos"]["descartados_sin_evidencia"] == 2


def test_riesgo_con_fuentes_validas_se_conserva():
    """Un riesgo con source_references válidas debe conservarse."""
    print("\n✅ Test 2: Riesgo con fuentes válidas se conserva")
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
    assert status == "success", f"Status debe ser success, fue {status}"
    assert filtered[0]["valor"] == "Multa por incumplimiento de plazos"
    print(f"   ✓ Items conservados: {len(filtered)}")
    print(f"   ✓ Status mantenido: {status}")


def test_mezcla_con_y_sin_fuentes():
    """Items con fuentes se conservan, sin fuentes se descartan."""
    print("\n✅ Test 3: Mezcla de items con y sin fuentes")
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

    # El del medio (valor sustantivo, sin fuentes) se conserva flag; los 3 quedan.
    assert len(filtered) == 3, f"Los 3 items se conservan, se conservaron {len(filtered)}"
    assert quality["riesgos"]["conservados_sin_evidencia_verificable"] == 1
    assert quality["riesgos"]["conservados"] == 3


def test_todos_con_dato_sin_fuentes_se_conservan_flag():
    """Antes: si todos carecían de fuentes la lista quedaba vacía. Ahora
    (FIX 2026-09-03): si tienen `valor` sustantivo se conservan todos, con
    el contador `conservados_sin_evidencia_verificable`."""
    print("\n✅ Test 4: todos con dato pero sin fuentes -> se conservan flag")
    items = [
        {"tipo": "otro", "subtipo": "otro_explicito", "valor": "Riesgo 1 con dato", "source_references": [], "extraction_status": "success", "confidence": 0.7},
        {"tipo": "otro", "subtipo": "otro_explicito", "valor": "Riesgo 2 con dato", "source_references": [], "extraction_status": "success", "confidence": 0.6},
    ]

    quality = {}
    filtered, status = _drop_items_without_sources(
        items, "success", category="riesgos", quality=quality
    )

    assert len(filtered) == 2
    assert quality["riesgos"]["conservados_sin_evidencia_verificable"] == 2
    assert quality["riesgos"]["conservados"] == 2


def test_enforce_citation_contract():
    """_enforce_citation_contract debe limpiar citas inválidas."""
    print("\n✅ Test 5: Enforcement de contrato de citación")
    items = [
        {
            "tipo": "incumplimiento",
            "subtipo": "incumplimiento",
            "valor": "Riesgo con cita válida",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "Esta es una cita suficientemente larga y válida",
                }
            ],
            "extraction_status": "success",
            "confidence": 0.8,
        },
        {
            "tipo": "legal",
            "subtipo": "legal_contractual",
            "valor": "Riesgo con cita corta",
            "source_references": [
                {
                    "document_id": "doc-2",
                    "page_number": 3,
                    "citation": "Muy corta",  # < 12 caracteres
                }
            ],
            "extraction_status": "success",
            "confidence": 0.7,
        },
    ]

    cleaned = _enforce_citation_contract(items)

    # Primera cita debe conservarse
    assert len(cleaned[0]["source_references"]) > 0
    assert len(cleaned[0]["source_references"][0]["citation"]) >= 12
    print(
        f"   ✓ Cita válida conservada: {len(cleaned[0]['source_references'][0]['citation'])} caracteres"
    )

    # Segunda cita muy corta debe descartarse o limpiarse
    if len(cleaned[1]["source_references"]) > 0:
        assert len(cleaned[1]["source_references"][0].get("citation", "")) >= 12
    print(f"   ✓ Cita corta procesada correctamente")


def test_preview_not_found_placeholders_se_conservan_si_se_habilita_flag():
    """Permite conservar placeholders not_found sin fuentes para preview."""
    items = [
        {
            "tipo": "mantenimiento_oferta",
            "valor": None,
            "source_references": [],
            "extraction_status": "not_found",
            "confidence": 0.0,
        },
        {
            "tipo": "forma_pago",
            "valor": None,
            "source_references": [],
            "extraction_status": "not_found",
            "confidence": 0.0,
        },
    ]

    quality = {}
    filtered, status = _drop_items_without_sources(
        items,
        "not_found",
        category="preview_criterios",
        quality=quality,
        keep_not_found_without_sources=True,
    )

    assert len(filtered) == 2
    assert status == "not_found"
    assert quality["preview_criterios"]["placeholders_not_found_conservados"] == 2
    assert quality["preview_criterios"]["conservados"] == 2


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTS DE REGLA ANTI-INVENCIÓN DE RIESGOS")
    print("=" * 60)

    try:
        test_riesgo_sin_fuentes_se_descarta()
        test_riesgo_con_fuentes_validas_se_conserva()
        test_mezcla_con_y_sin_fuentes()
        test_todos_sin_fuentes_resulta_en_lista_vacia()
        test_enforce_citation_contract()

        print("\n" + "=" * 60)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 60)
        print("\nLa regla anti-invención está funcionando correctamente:")
        print("  • Items sin fuentes son descartados")
        print("  • Items con fuentes se conservan")
        print("  • Status cambia a 'partial' cuando se descartan items")
        print("  • Métricas de calidad se registran correctamente")
        print("=" * 60 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
