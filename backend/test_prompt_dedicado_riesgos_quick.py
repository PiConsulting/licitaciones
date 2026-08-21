"""
Test del prompt dedicado de Riesgos.
Valida que el prompt cumple los criterios de calidad de R2.2.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.extractors.base import (
    CANONICAL_PROMPT_FILES,
    CANONICAL_CATEGORY_PROMPT_MAP,
    _load_prompt
)


def test_prompt_existe_y_registrado():
    """Verifica que riesgos.txt existe y está registrado correctamente."""
    print("\n✅ Test 1: Prompt existe y está registrado")
    
    # Verificar que está en el inventario de prompts canónicos
    assert "riesgos.txt" in CANONICAL_PROMPT_FILES, "riesgos.txt debe estar en CANONICAL_PROMPT_FILES"
    print("   ✓ Registrado en CANONICAL_PROMPT_FILES")
    
    # Verificar que está en el mapping de categorías
    assert "riesgos" in CANONICAL_CATEGORY_PROMPT_MAP, "riesgos debe estar en CANONICAL_CATEGORY_PROMPT_MAP"
    assert CANONICAL_CATEGORY_PROMPT_MAP["riesgos"] == "riesgos.txt", "Mapping debe apuntar a riesgos.txt"
    print("   ✓ Registrado en CANONICAL_CATEGORY_PROMPT_MAP")
    
    # Verificar que el archivo existe y se puede cargar
    prompt_content = _load_prompt("riesgos.txt")
    assert len(prompt_content) > 0, "El prompt no debe estar vacío"
    print(f"   ✓ Archivo cargado exitosamente ({len(prompt_content)} caracteres)")


def test_estructura_dedicada():
    """Verifica que el prompt tiene estructura dedicada a Riesgos."""
    print("\n✅ Test 2: Estructura dedicada")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Secciones obligatorias
    required_sections = [
        "# CONCEPTO DE LA CATEGORÍA",
        "# OBJETIVO",
        "# CHUNKS DEL PLIEGO",
        "# INSTRUCCIONES DE EXTRACCIÓN",
        "# FORMATO DE SALIDA",
        "# VALIDACIÓN DE CALIDAD"
    ]
    
    for section in required_sections:
        assert section in prompt, f"Sección '{section}' debe estar presente"
        print(f"   ✓ Sección presente: {section}")


def test_enfoque_en_evidencia():
    """Verifica que el prompt enfatiza evidencia verificable (AC1)."""
    print("\n✅ Test 3: Enfoque en evidencia verificable (AC1)")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Frases clave que demuestran énfasis en evidencia
    evidence_keywords = [
        "source_references",
        "citas textuales",
        "respaldado",
        "verificable",
        "literal del pliego",
        "No inventes"
    ]
    
    found = []
    for keyword in evidence_keywords:
        if keyword.lower() in prompt.lower():
            found.append(keyword)
            print(f"   ✓ Énfasis en evidencia: '{keyword}' presente")
    
    coverage = (len(found) / len(evidence_keywords)) * 100
    assert coverage >= 80, f"Cobertura de énfasis en evidencia debe ser >= 80%, fue {coverage:.0f}%"
    print(f"\n   Cobertura: {len(found)}/{len(evidence_keywords)} ({coverage:.0f}%)")


def test_regla_sin_evidencia():
    """Verifica que el prompt instruye qué hacer sin evidencia (AC2)."""
    print("\n✅ Test 4: Instrucción explícita sin evidencia (AC2)")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Debe instruir explícitamente qué hacer cuando no hay riesgos
    assert "not_found" in prompt, "Debe mencionar 'not_found'"
    assert "NO encontrás" in prompt or "no encontras" in prompt.lower(), "Debe instruir qué hacer cuando NO encuentra riesgos"
    
    # Verificar que instruye devolver lista vacía
    assert "[]" in prompt, "Debe instruir devolver lista vacía cuando no hay hallazgos"
    
    print("   ✓ Instrucción presente: qué hacer sin evidencia")
    print("   ✓ Estado 'not_found' especificado")
    print("   ✓ Formato de lista vacía [] especificado")


def test_formato_estructurado():
    """Verifica que define formato JSON estructurado claro."""
    print("\n✅ Test 5: Formato estructurado definido")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Campos obligatorios del formato
    required_fields = [
        "tipo",
        "subtipo",
        "valor",
        "extraction_status",
        "source_references",
        "document_id",
        "page_number",
        "citation"
    ]
    
    for field in required_fields:
        assert f'"{field}"' in prompt, f"Campo '{field}' debe estar en el formato de salida"
        print(f"   ✓ Campo definido: {field}")


def test_subtipos_definidos():
    """Verifica que los subtipos están claramente definidos."""
    print("\n✅ Test 6: Subtipos definidos")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Subtipos esperados
    expected_subtypes = [
        "ejecucion",
        "incumplimiento",
        "operativo",
        "plazos",
        "economico",
        "tecnico",
        "legal_contractual",
        "otro_explicito"
    ]
    
    for subtype in expected_subtypes:
        assert subtype in prompt, f"Subtipo '{subtype}' debe estar definido"
        print(f"   ✓ Subtipo definido: {subtype}")


def test_reconocimiento_semantico():
    """Verifica que incluye guía de reconocimiento semántico."""
    print("\n✅ Test 7: Reconocimiento semántico")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Debe incluir frases típicas que ayuden al LLM a reconocer riesgos
    semantic_patterns = [
        "incumplimiento",
        "multas",
        "penalizaciones",
        "rescind",
        "responsable"
    ]
    
    found = 0
    for pattern in semantic_patterns:
        if pattern.lower() in prompt.lower():
            found += 1
            print(f"   ✓ Patrón semántico presente: '{pattern}'")
    
    coverage = (found / len(semantic_patterns)) * 100
    assert coverage >= 60, f"Cobertura semántica debe ser >= 60%, fue {coverage:.0f}%"
    print(f"\n   Cobertura semántica: {found}/{len(semantic_patterns)} ({coverage:.0f}%)")


def test_diferenciacion_categorias():
    """Verifica que diferencia Riesgos de otras categorías."""
    print("\n✅ Test 8: Diferenciación de categorías")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Debe mencionar qué NO incluir para evitar confusión
    differentiation_terms = [
        "No confundir",
        "Causales de rechazo",
        "Requisitos",
        "Garantías"
    ]
    
    found = 0
    for term in differentiation_terms:
        if term in prompt:
            found += 1
            print(f"   ✓ Diferenciación presente: '{term}'")
    
    assert found >= 2, f"Debe diferenciar al menos de 2 categorías, encontró {found}"
    print(f"\n   Diferenciación de {found} categorías")


def test_validacion_calidad():
    """Verifica que incluye reglas de validación de calidad."""
    print("\n✅ Test 9: Reglas de validación de calidad")
    
    prompt = _load_prompt("riesgos.txt")
    
    # Reglas de validación esperadas
    validation_rules = [
        "DEBE estar respaldado",
        "literales del pliego",
        "No inventes",
        "consolidalo"
    ]
    
    found = 0
    for rule in validation_rules:
        if rule in prompt:
            found += 1
            print(f"   ✓ Regla de validación: '{rule}'")
    
    coverage = (found / len(validation_rules)) * 100
    assert coverage >= 75, f"Cobertura de reglas debe ser >= 75%, fue {coverage:.0f}%"
    print(f"\n   Cobertura de reglas: {found}/{len(validation_rules)} ({coverage:.0f}%)")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE PROMPT DEDICADO PARA RIESGOS")
    print("=" * 70)
    
    try:
        test_prompt_existe_y_registrado()
        test_estructura_dedicada()
        test_enfoque_en_evidencia()
        test_regla_sin_evidencia()
        test_formato_estructurado()
        test_subtipos_definidos()
        test_reconocimiento_semantico()
        test_diferenciacion_categorias()
        test_validacion_calidad()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nEl prompt dedicado de Riesgos cumple todos los criterios:")
        print("  ✓ AC1: Items estructurados sin inferencias no respaldadas")
        print("  ✓ AC2: Explicita ausencia de riesgos cuando no hay evidencia")
        print("\nCaracterísticas del prompt:")
        print("  • Estructura dedicada con 6 secciones claras")
        print("  • Énfasis fuerte en evidencia verificable")
        print("  • Formato JSON estructurado con 8 subtipos")
        print("  • Reconocimiento semántico de patrones de riesgo")
        print("  • Diferenciación clara de otras categorías")
        print("  • Reglas de validación de calidad explícitas")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
