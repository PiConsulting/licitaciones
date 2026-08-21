"""
Test de integración para mensaje sin riesgos.
Verifica que cuando no hay riesgos con evidencia, se muestra mensaje apropiado.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.synthesis import _empty_category_narrative, CATEGORY_LABELS
from analysis.extraction.schemas import CONFIDENCE_NO_EVIDENCE


def test_mensaje_sin_riesgos():
    """Cuando no hay riesgos, debe mostrarse mensaje canónico."""
    print("\n✅ Test: Mensaje cuando no se encuentran riesgos")
    
    category_label = CATEGORY_LABELS["riesgos"]
    narrative = _empty_category_narrative(category_label)
    
    # Verificar estructura
    assert narrative.blocks is not None, "Debe tener blocks"
    assert len(narrative.blocks) == 1, "Debe tener exactamente 1 block"
    assert narrative.blocks[0].type == "paragraph", "Block debe ser de tipo paragraph"
    
    # Verificar mensaje
    expected_text = f"No se encontró información sobre {category_label} en los documentos del pliego."
    assert narrative.blocks[0].text == expected_text, f"Mensaje incorrecto: {narrative.blocks[0].text}"
    
    # Verificar confianza
    assert narrative.blocks[0].confidence_level == CONFIDENCE_NO_EVIDENCE, "Confianza debe ser CONFIDENCE_NO_EVIDENCE"
    
    # Verificar fuentes vacías
    assert narrative.blocks[0].source_ids == [], "source_ids debe estar vacío"
    assert narrative.sources == [], "sources debe estar vacío"
    
    print(f'   ✓ Mensaje: "{narrative.blocks[0].text}"')
    print(f"   ✓ Confianza: {narrative.blocks[0].confidence_level}")
    print(f"   ✓ Fuentes vacías: {len(narrative.sources)} fuentes")


def test_formato_mensaje_todas_categorias():
    """Verifica que el formato del mensaje sea consistente para todas las categorías."""
    print("\n✅ Test: Formato consistente para todas las categorías")
    
    for category_key, category_label in CATEGORY_LABELS.items():
        narrative = _empty_category_narrative(category_label)
        
        # Verificar que sigue el patrón estándar
        assert "No se encontró información sobre" in narrative.blocks[0].text
        assert category_label in narrative.blocks[0].text
        assert "en los documentos del pliego" in narrative.blocks[0].text
        assert narrative.blocks[0].confidence_level == CONFIDENCE_NO_EVIDENCE
        assert len(narrative.sources) == 0
    
    print(f"   ✓ {len(CATEGORY_LABELS)} categorías verificadas")
    print("   ✓ Todas tienen formato consistente")


def test_mensaje_riesgos_texto_exacto():
    """Verifica el texto exacto para la categoría Riesgos."""
    print("\n✅ Test: Texto exacto del mensaje de Riesgos")
    
    narrative = _empty_category_narrative("Riesgos")
    expected = "No se encontró información sobre Riesgos en los documentos del pliego."
    
    assert narrative.blocks[0].text == expected
    print(f'   ✓ Texto exacto: "{expected}"')


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTS DE MENSAJE SIN RIESGOS")
    print("=" * 60)
    
    try:
        test_mensaje_sin_riesgos()
        test_formato_mensaje_todas_categorias()
        test_mensaje_riesgos_texto_exacto()
        
        print("\n" + "=" * 60)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 60)
        print("\nMensaje sin riesgos funciona correctamente:")
        print("  • Texto canónico apropiado")
        print("  • Confianza correcta (CONFIDENCE_NO_EVIDENCE)")
        print("  • Sin fuentes (sources = [])")
        print("  • Formato consistente con otras categorías")
        print("=" * 60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
