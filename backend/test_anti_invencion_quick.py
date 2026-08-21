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

from analysis.extraction.graph import _drop_items_without_sources, _enforce_citation_contract


def test_riesgo_sin_fuentes_se_descarta():
    """Un riesgo sin source_references debe ser descartado."""
    print("\n✅ Test 1: Riesgo sin fuentes se descarta")
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
    assert status == "partial", f"Status debería ser partial, fue {status}"
    print(f"   ✓ Items descartados: {len(items) - len(filtered)}")
    print(f"   ✓ Status cambiado a: {status}")


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
    
    assert len(filtered) == 2, f"Solo 2 items deben conservarse, se conservaron {len(filtered)}"
    assert status == "partial", f"Status debe ser partial, fue {status}"
    assert quality["riesgos"]["descartados_sin_evidencia"] == 1
    assert quality["riesgos"]["conservados"] == 2
    print(f"   ✓ Items conservados: {len(filtered)}")
    print(f"   ✓ Items descartados: {quality['riesgos']['descartados_sin_evidencia']}")
    print(f"   ✓ Status cambiado a: {status}")


def test_todos_sin_fuentes_resulta_en_lista_vacia():
    """Si todos los items carecen de fuentes, la lista queda vacía."""
    print("\n✅ Test 4: Todos los items sin fuentes resulta en lista vacía")
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
    assert status == "partial", f"Status debe ser partial, fue {status}"
    assert quality["riesgos"]["descartados_sin_evidencia"] == 2
    assert quality["riesgos"]["conservados"] == 0
    print(f"   ✓ Items conservados: {len(filtered)}")
    print(f"   ✓ Items descartados: {quality['riesgos']['descartados_sin_evidencia']}")
    print(f"   ✓ Status final: {status}")


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
    print(f"   ✓ Cita válida conservada: {len(cleaned[0]['source_references'][0]['citation'])} caracteres")
    
    # Segunda cita muy corta debe descartarse o limpiarse
    if len(cleaned[1]["source_references"]) > 0:
        assert len(cleaned[1]["source_references"][0].get("citation", "")) >= 12
    print(f"   ✓ Cita corta procesada correctamente")


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
