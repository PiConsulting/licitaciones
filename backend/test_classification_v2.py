"""
Script de validación para el nuevo sistema de clasificación basado en scoring de densidad.
Prueba con chunks reales que antes estaban mal clasificados.
"""
import sys
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from extraction.chunking import classify_chunk_categories

# Test Case 1: Chunk con causales de rechazo (antes clasificado como criterios_evaluacion)
chunk_rechazo = {
    "chunk_id": "test_1",
    "heading_path": ["EVALUACIÓN DE LAS OFERTAS"],
    "content": """
    Queda debidamente establecido a los fines de comparar las ofertas que se presenten, que se deberán
    considerar únicamente aquellas ofertas que cumplan con todos los requisitos exigidos en el presente pliego.
    
    Las ofertas que no cumplan con los requisitos mínimos establecidos serán rechazadas sin más trámite.
    Asimismo, quedará excluida toda oferta que presente información falsa o que incurra en prácticas
    anticompetitivas. La Comisión Evaluadora se reserva el derecho de desestimar cualquier oferta que
    no se ajuste a las especificaciones técnicas solicitadas.
    """
}

# Test Case 2: Chunk con anexos obligatorios (antes clasificado como requisitos_admisibilidad)
chunk_anexos = {
    "chunk_id": "test_2",
    "heading_path": ["DOCUMENTACIÓN A PRESENTAR"],
    "content": """
    Los oferentes deberán presentar la siguiente documentación:
    
    a) Formulario de Inscripción (Anexo I) debidamente completado y firmado
    b) Declaración Jurada de no encontrarse inhabilitado (Anexo II)
    c) Planilla de cotización según modelo adjunto (Anexo III)
    
    Todos los formularios deben ser completados sin tachaduras ni enmiendas. Los anexos son de
    presentación obligatoria y deberán estar firmados por el representante legal.
    """
}

# Test Case 3: Chunk con múltiples categorías (ambiguo)
chunk_ambiguo = {
    "chunk_id": "test_3",
    "heading_path": ["REQUISITOS DE ADMISIBILIDAD"],
    "content": """
    Los oferentes deberán presentar toda la documentación requerida dentro del plazo establecido.
    La no presentación de algún documento en el plazo indicado será causal de rechazo de la oferta.
    
    Se considerará inadmisible toda oferta que no incluya la garantía de mantenimiento de oferta
    por el monto y plazo especificados. El oferente que presente documentación apócrifa será excluido
    del proceso licitatorio y se le iniciará las acciones legales correspondientes.
    """
}

def print_classification_result(chunk_name: str, result: dict):
    print(f"\n{'='*80}")
    print(f"TEST: {chunk_name}")
    print(f"{'='*80}")
    print(f"Heading Path: {' > '.join(result.get('heading_path', ['N/A']))}")
    print(f"\nPrimary Category: {result['primary_category']}")
    print(f"Secondary Categories: {result['secondary_categories']}")
    print(f"\nCategory Scores:")
    for cat, score in sorted(result['category_scores'].items(), key=lambda x: x[1], reverse=True):
        bar = '█' * int(score * 40)
        print(f"  {cat:30s} {score:0.3f} {bar}")

if __name__ == "__main__":
    print("\n🧪 TESTING NUEVO SISTEMA DE CLASIFICACIÓN v2 (DENSITY SCORING)")
    print("="*80)
    
    # Test 1: Causales de rechazo
    result1 = classify_chunk_categories(chunk_rechazo)
    result1['heading_path'] = chunk_rechazo['heading_path']
    print_classification_result("Chunk con Causales de Rechazo", result1)
    
    # Verificación
    assert "causales_rechazo" in [result1['primary_category']] + result1['secondary_categories'], \
        "❌ FALLO: causales_rechazo no está en primary ni secondary"
    print("\n✅ PASS: causales_rechazo detectado correctamente")
    
    # Test 2: Anexos obligatorios
    result2 = classify_chunk_categories(chunk_anexos)
    result2['heading_path'] = chunk_anexos['heading_path']
    print_classification_result("Chunk con Anexos Obligatorios", result2)
    
    # Verificación
    assert "anexos_obligatorios" in [result2['primary_category']] + result2['secondary_categories'], \
        "❌ FALLO: anexos_obligatorios no está en primary ni secondary"
    print("\n✅ PASS: anexos_obligatorios detectado correctamente")
    
    # Test 3: Chunk ambiguo (múltiples categorías)
    result3 = classify_chunk_categories(chunk_ambiguo)
    result3['heading_path'] = chunk_ambiguo['heading_path']
    print_classification_result("Chunk Ambiguo (Múltiples Categorías)", result3)
    
    # Verificación: debe tener múltiples secondary categories
    all_cats = [result3['primary_category']] + result3['secondary_categories']
    assert "causales_rechazo" in all_cats, "❌ FALLO: causales_rechazo no detectado en chunk ambiguo"
    assert "requisitos_admisibilidad" in all_cats, "❌ FALLO: requisitos_admisibilidad no detectado"
    assert len(result3['secondary_categories']) >= 1, "❌ FALLO: no hay secondary categories en chunk ambiguo"
    print("\n✅ PASS: Chunk ambiguo clasificado con múltiples categorías")
    
    print("\n" + "="*80)
    print("🎉 TODOS LOS TESTS PASARON - Sistema de clasificación v2 funcionando correctamente")
    print("="*80)
