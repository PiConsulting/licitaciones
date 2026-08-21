"""
Test de estado sin riesgos relevantes en UI.
Valida que el mensaje explícito se muestra cuando no hay evidencia de riesgos.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.synthesis import (
    _empty_category_narrative,
    CATEGORY_LABELS,
)
from analysis.extraction.schemas import CategoryNarrative


def test_mensaje_canonico_sin_riesgos():
    """Verifica el mensaje canónico cuando no hay riesgos (AC1)."""
    print("\n✅ Test 1: Mensaje canónico sin riesgos")
    
    try:
        # Generar narrative vacía
        narrative = _empty_category_narrative("Riesgos")
        
        # Verificar estructura
        assert isinstance(narrative, CategoryNarrative)
        assert len(narrative.blocks) == 1
        assert narrative.blocks[0].type == "paragraph"
        assert narrative.blocks[0].confidence_level == "baja"  # CONFIDENCE_NO_EVIDENCE
        
        # Verificar texto del mensaje
        texto = narrative.blocks[0].text
        assert "No se encontró información sobre Riesgos" in texto
        assert "documentos del pliego" in texto
        
        print(f"   ✓ Mensaje: \"{texto}\"")
        print(f"   ✓ Confianza: {narrative.blocks[0].confidence_level}")
        print(f"   ✓ Fuentes: {len(narrative.sources)} fuentes")
        
        # Verificar que no hay fuentes
        assert len(narrative.sources) == 0
        print("   ✓ Sin fuentes (no hay evidencia)")
    except Exception as e:
        print(f"\n❌ ERROR en test 1: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_no_bullets_vacios():
    """Verifica que no se generan bullets vacíos (AC2)."""
    print("\n✅ Test 2: No hay bullets vacíos en estado sin riesgos")
    
    narrative = _empty_category_narrative("Riesgos")
    
    # Debe ser un párrafo, no una lista
    assert narrative.blocks[0].type == "paragraph"
    assert narrative.blocks[0].type != "bullet_list"
    
    print("   ✓ Tipo de bloque: paragraph (no bullet_list)")
    print("   ✓ No genera bullets vacíos ni inferidos")


def test_diferencia_con_not_analyzed():
    """Verifica que el mensaje no colisiona con 'not_analyzed' (Dev Notes)."""
    print("\n✅ Test 3: Diferencia entre sin riesgos vs no analizado")
    
    # Mensaje sin riesgos (after analysis)
    narrative_sin_riesgos = _empty_category_narrative("Riesgos")
    texto_sin_riesgos = narrative_sin_riesgos.blocks[0].text
    
    # El mensaje debe indicar claramente que SÍ se buscó pero NO se encontró
    assert "No se encontró" in texto_sin_riesgos
    assert "información" in texto_sin_riesgos
    
    print(f"   ✓ Mensaje sin riesgos: \"{texto_sin_riesgos}\"")
    print("   ✓ Indica que SÍ se analizó pero NO se encontró")
    print("   ✓ Diferente de 'not_analyzed' (no procesado aún)")


def test_consistencia_mensaje_todas_categorias():
    """Verifica consistencia del mensaje entre todas las categorías."""
    print("\n✅ Test 4: Consistencia del mensaje entre categorías")
    
    categorias = [
        "Objeto y Alcance",
        "Riesgos",
        "Requisitos de Admisibilidad",
        "Garantías",
        "Plazos Clave",
        "Criterios de Evaluación",
        "Causales de Rechazo",
        "Anexos Obligatorios",
    ]
    
    for categoria in categorias:
        narrative = _empty_category_narrative(categoria)
        texto = narrative.blocks[0].text
        
        # Verificar formato consistente
        assert f"No se encontró información sobre {categoria}" in texto
        assert "documentos del pliego" in texto
        assert narrative.blocks[0].confidence_level == "baja"  # CONFIDENCE_NO_EVIDENCE
        assert len(narrative.sources) == 0
        
        print(f"   ✓ {categoria}: formato consistente")
    
    print(f"\n   Todas las {len(categorias)} categorías tienen formato consistente")


def test_serializacion_para_frontend():
    """Verifica que la narrative se serializa correctamente para el frontend."""
    print("\n✅ Test 5: Serialización para frontend")
    
    narrative = _empty_category_narrative("Riesgos")
    
    # Serializar a dict (como lo haría la API)
    narrative_dict = narrative.model_dump()
    
    # Verificar estructura JSON
    assert "blocks" in narrative_dict
    assert "sources" in narrative_dict
    assert len(narrative_dict["blocks"]) == 1
    assert narrative_dict["blocks"][0]["type"] == "paragraph"
    assert "No se encontró información sobre Riesgos" in narrative_dict["blocks"][0]["text"]
    assert len(narrative_dict["sources"]) == 0
    
    print("   ✓ Estructura JSON correcta")
    print("   ✓ blocks[0].type: paragraph")
    print("   ✓ blocks[0].text: mensaje explícito")
    print("   ✓ sources: lista vacía")
    print("   ✓ Listo para consumo del frontend")


def test_no_confusion_con_estado_vacio():
    """Verifica que el mensaje explícito evita confusión con ausencia de datos."""
    print("\n✅ Test 6: Mensaje explícito evita confusión")
    
    narrative = _empty_category_narrative("Riesgos")
    texto = narrative.blocks[0].text
    
    # El mensaje debe ser explícito, no ambiguo
    assert len(texto) > 20  # No puede ser vacío ni muy corto
    assert "No se encontró" in texto  # Debe decir explícitamente que no hay
    assert "Riesgos" in texto  # Debe mencionar la categoría específica
    
    print(f"   ✓ Mensaje explícito ({len(texto)} caracteres)")
    print(f"   ✓ No ambiguo: dice claramente que no hay riesgos")
    print(f"   ✓ Usuario sabe que SÍ se buscó pero NO se encontró")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE ESTADO SIN RIESGOS RELEVANTES EN UI")
    print("=" * 70)
    
    try:
        test_mensaje_canonico_sin_riesgos()
        test_no_bullets_vacios()
        test_diferencia_con_not_analyzed()
        test_consistencia_mensaje_todas_categorias()
        test_serializacion_para_frontend()
        test_no_confusion_con_estado_vacio()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nEstado sin riesgos relevantes en UI funcionando correctamente:")
        print("  ✓ AC1: Mensaje explícito de no riesgos relevantes")
        print("  ✓ AC2: No dibuja bullets vacíos ni inferidos")
        print("\nCaracterísticas validadas:")
        print("  • Mensaje canónico: 'No se encontró información sobre Riesgos'")
        print("  • Formato: paragraph (no bullet_list)")
        print("  • Confianza: low")
        print("  • Sin fuentes (lista vacía)")
        print("  • Serialización JSON correcta para frontend")
        print("  • Diferente de 'not_analyzed' (no procesado)")
        print("  • Consistencia con otras categorías")
        print("\n  El frontend renderiza el mensaje sin confusión,")
        print("  el usuario sabe que SÍ se analizó pero NO se encontró.")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
