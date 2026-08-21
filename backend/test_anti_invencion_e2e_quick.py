"""
Test end-to-end de anti-invención de riesgos.
Demuestra el flujo completo: extracción → descarte por falta de evidencia → mensaje apropiado.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.graph import _drop_items_without_sources
from analysis.extraction.synthesis import _empty_category_narrative, CATEGORY_LABELS


def test_flujo_completo_sin_evidencia():
    """
    Simula el flujo completo cuando el LLM extrae riesgos pero sin evidencia verificable.
    
    Flujo:
    1. Extractor genera riesgos (posiblemente alucinados)
    2. merge_node los descarta por falta de evidencia
    3. synthesis.py genera mensaje apropiado
    """
    print("\n✅ Test E2E: Flujo completo de anti-invención")
    print("   Escenario: LLM extrae riesgos pero sin evidencia verificable\n")
    
    # 1. Riesgos extraídos (posiblemente inventados)
    print("   [1] Extractor genera riesgos:")
    extracted_items = [
        {
            "tipo": "descalificacion",
            "subtipo": "plazos",
            "valor": "Riesgo de descalificación por entrega tardía",
            "source_references": [],  # SIN EVIDENCIA
            "extraction_status": "success",
            "confidence": 0.8,
        },
        {
            "tipo": "economico",
            "subtipo": "economico",
            "valor": "Posible multa por incumplimiento",
            "source_references": [],  # SIN EVIDENCIA
            "extraction_status": "success",
            "confidence": 0.7,
        },
    ]
    print(f"       • {len(extracted_items)} riesgos extraídos")
    for item in extracted_items:
        print(f"       • {item['valor']} [{item['tipo']}/{item['subtipo']}]")
    
    # 2. merge_node aplica regla de evidencia
    print("\n   [2] merge_node aplica regla anti-invención:")
    quality = {}
    filtered_items, status = _drop_items_without_sources(
        extracted_items, 
        "success", 
        category="riesgos",
        quality=quality
    )
    print(f"       • Items conservados: {len(filtered_items)}")
    print(f"       • Items descartados: {quality['riesgos']['descartados_sin_evidencia']}")
    print(f"       • Status final: {status}")
    
    # Verificaciones de merge_node
    assert len(filtered_items) == 0, "Todos los items sin evidencia deben descartarse"
    assert status == "partial", "Status debe cambiar a partial"
    assert quality["riesgos"]["descartados_sin_evidencia"] == 2
    
    # 3. synthesis.py genera mensaje apropiado
    print("\n   [3] synthesis.py genera mensaje canónico:")
    category_label = CATEGORY_LABELS["riesgos"]
    narrative = _empty_category_narrative(category_label)
    
    print(f'       • Mensaje: "{narrative.blocks[0].text}"')
    print(f"       • Confianza: {narrative.blocks[0].confidence_level}")
    print(f"       • Fuentes: {len(narrative.sources)} fuentes")
    
    # Verificaciones de synthesis
    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "paragraph"
    assert "No se encontró información sobre Riesgos" in narrative.blocks[0].text
    assert len(narrative.sources) == 0
    assert narrative.blocks[0].confidence_level == "baja"
    
    print("\n   ✓ Flujo completo funciona correctamente")
    print("   ✓ Usuario ve mensaje apropiado en lugar de riesgos inventados")


def test_flujo_completo_con_evidencia():
    """
    Simula el flujo completo cuando hay riesgos CON evidencia verificable.
    
    Flujo:
    1. Extractor genera riesgos con fuentes válidas
    2. merge_node los conserva
    3. synthesis.py los renderiza normalmente (no genera mensaje vacío)
    """
    print("\n✅ Test E2E: Flujo con evidencia verificable")
    print("   Escenario: LLM extrae riesgos respaldados por evidencia\n")
    
    # 1. Riesgos con evidencia
    print("   [1] Extractor genera riesgos con evidencia:")
    extracted_items = [
        {
            "tipo": "economico",
            "subtipo": "economico",
            "valor": "Multa del 10% del valor del contrato por incumplimiento de plazos",
            "source_references": [
                {
                    "document_id": "doc-123",
                    "page_number": 15,
                    "citation": "Por cada día de demora se aplicará una multa equivalente al 0.1% del valor total del contrato",
                }
            ],
            "extraction_status": "success",
            "confidence": 0.95,
        },
    ]
    print(f"       • {len(extracted_items)} riesgo extraído")
    print(f"       • {extracted_items[0]['valor']}")
    print(f"       • Con evidencia: página {extracted_items[0]['source_references'][0]['page_number']}")
    
    # 2. merge_node conserva items con evidencia
    print("\n   [2] merge_node conserva items con evidencia:")
    quality = {}
    filtered_items, status = _drop_items_without_sources(
        extracted_items,
        "success",
        category="riesgos",
        quality=quality
    )
    print(f"       • Items conservados: {len(filtered_items)}")
    print(f"       • Items descartados: {quality['riesgos'].get('descartados_sin_evidencia', 0)}")
    print(f"       • Status final: {status}")
    
    # Verificaciones
    assert len(filtered_items) == 1, "Item con evidencia debe conservarse"
    assert status == "success", "Status debe mantenerse como success"
    assert quality["riesgos"]["conservados"] == 1
    assert quality["riesgos"].get("descartados_sin_evidencia", 0) == 0
    
    print("\n   ✓ Items con evidencia se conservan correctamente")
    print("   ✓ Usuario ve riesgos reales respaldados por el pliego")


def test_flujo_mixto():
    """
    Flujo mixto: algunos riesgos con evidencia, otros sin evidencia.
    """
    print("\n✅ Test E2E: Flujo mixto (algunos con evidencia, otros sin)")
    print("   Escenario: Mezcla de riesgos verificables y posibles invenciones\n")
    
    extracted_items = [
        {
            "tipo": "economico",
            "subtipo": "economico",
            "valor": "Multa verificable en pliego",
            "source_references": [
                {"document_id": "doc-1", "page_number": 10, "citation": "Evidencia verificable de multa"}
            ],
            "extraction_status": "success",
            "confidence": 0.9,
        },
        {
            "tipo": "operativo",
            "subtipo": "operativo",
            "valor": "Riesgo inventado sin evidencia",
            "source_references": [],  # SIN EVIDENCIA
            "extraction_status": "success",
            "confidence": 0.7,
        },
        {
            "tipo": "legal",
            "subtipo": "legal_contractual",
            "valor": "Otra consecuencia verificable",
            "source_references": [
                {"document_id": "doc-1", "page_number": 12, "citation": "Otra evidencia verificable"}
            ],
            "extraction_status": "success",
            "confidence": 0.85,
        },
    ]
    
    print(f"   [1] Extractor genera {len(extracted_items)} riesgos:")
    print(f"       • 2 con evidencia verificable")
    print(f"       • 1 sin evidencia (posible invención)")
    
    quality = {}
    filtered_items, status = _drop_items_without_sources(
        extracted_items,
        "success",
        category="riesgos",
        quality=quality
    )
    
    print(f"\n   [2] merge_node procesa:")
    print(f"       • Items conservados: {len(filtered_items)}")
    print(f"       • Items descartados: {quality['riesgos']['descartados_sin_evidencia']}")
    print(f"       • Status: {status}")
    
    # Verificaciones
    assert len(filtered_items) == 2, "Solo items con evidencia deben conservarse"
    assert status == "partial", "Status debe ser partial (hubo descartes)"
    assert quality["riesgos"]["descartados_sin_evidencia"] == 1
    assert quality["riesgos"]["conservados"] == 2
    
    print("\n   ✓ Solo riesgos verificables llegan al usuario")
    print("   ✓ Invenciones descartadas correctamente")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS END-TO-END: ANTI-INVENCIÓN DE RIESGOS")
    print("=" * 70)
    
    try:
        test_flujo_completo_sin_evidencia()
        test_flujo_completo_con_evidencia()
        test_flujo_mixto()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS E2E PASARON")
        print("=" * 70)
        print("\nLa regla anti-invención funciona en el flujo completo:")
        print("  ✓ Riesgos sin evidencia se descartan")
        print("  ✓ Riesgos con evidencia se conservan")
        print("  ✓ Mensaje apropiado cuando no hay evidencia")
        print("  ✓ Status correcto (success/partial según caso)")
        print("  ✓ Métricas de calidad registradas")
        print("\n  El usuario NUNCA ve riesgos inventados - solo los respaldados")
        print("  por evidencia verificable en el pliego.")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
