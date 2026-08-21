"""
Test rápido de query expansion para Riesgos.
Valida que los términos del glossary se cargan y aplican correctamente.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.glossary import (
    build_keyword_query,
    get_category_terms,
    get_category_top_k
)


def test_riesgos_glossary_cargado():
    """Verifica que la entrada 'riesgos' existe en el glossary."""
    print("\n✅ Test 1: Entrada 'riesgos' en glossary")
    
    terms = get_category_terms("riesgos")
    
    assert len(terms) > 0, "Debe haber términos definidos para riesgos"
    print(f"   ✓ {len(terms)} términos cargados")
    print(f"   ✓ Primeros términos: {', '.join(terms[:5])}")


def test_query_terms_principales():
    """Verifica que los query_terms principales están presentes."""
    print("\n✅ Test 2: Query terms principales")
    
    terms = get_category_terms("riesgos")
    terms_lower = [t.lower() for t in terms]
    
    expected_core_terms = [
        "multa",
        "penalizacion",
        "sancion",
        "incumplimiento",
        "rescision"
    ]
    
    for term in expected_core_terms:
        assert any(term in t_lower for t_lower in terms_lower), f"Término '{term}' debe estar en el glossary"
        print(f"   ✓ Término '{term}' presente")


def test_aliases_expandidos():
    """Verifica que los aliases están expandiendo la cobertura."""
    print("\n✅ Test 3: Aliases expandidos")
    
    terms = get_category_terms("riesgos")
    terms_lower = [t.lower() for t in terms]
    
    expected_aliases = [
        "multa por incumplimiento",
        "rescision de contrato",
        "penalizacion economica",
        "consecuencia legal",
        "responsabilidad civil"
    ]
    
    for alias in expected_aliases:
        assert any(alias in t_lower for t_lower in terms_lower), f"Alias '{alias}' debe estar en el glossary"
        print(f"   ✓ Alias '{alias}' presente")


def test_build_keyword_query_construye_string():
    """Verifica que build_keyword_query construye el string correctamente."""
    print("\n✅ Test 4: Construcción de keyword query")
    
    keyword_query = build_keyword_query("riesgos")
    
    assert isinstance(keyword_query, str), "keyword_query debe ser string"
    assert len(keyword_query) > 0, "keyword_query no debe estar vacío"
    assert "multa" in keyword_query.lower(), "Debe contener término 'multa'"
    assert "incumplimiento" in keyword_query.lower(), "Debe contener término 'incumplimiento'"
    
    print(f"   ✓ Query construida con {len(keyword_query)} caracteres")
    print(f"   ✓ Query preview: {keyword_query[:100]}...")


def test_top_k_configurado():
    """Verifica que top_k está configurado para riesgos."""
    print("\n✅ Test 5: Top-K configurado")
    
    top_k = get_category_top_k("riesgos", default=25)
    
    assert top_k == 35, f"top_k debería ser 35, fue {top_k}"
    print(f"   ✓ top_k = {top_k} (configurado correctamente)")


def test_cobertura_terminos_contractuales():
    """Verifica cobertura de términos contractuales típicos."""
    print("\n✅ Test 6: Cobertura de términos contractuales")
    
    terms = get_category_terms("riesgos")
    terms_text = " ".join(terms).lower()
    
    contractual_patterns = [
        ("multa", "Multas y penalizaciones"),
        ("rescision", "Rescisión de contrato"),
        ("incumplimiento", "Incumplimientos"),
        ("responsabilidad", "Responsabilidades"),
        ("descalificacion", "Descalificación"),
        ("mora", "Mora y demoras"),
        ("garantia", "Ejecución de garantías"),
        ("daño", "Daños y perjuicios"),
    ]
    
    found = 0
    for pattern, description in contractual_patterns:
        if pattern in terms_text:
            found += 1
            print(f"   ✓ {description}: término '{pattern}' presente")
        else:
            print(f"   ⚠ {description}: término '{pattern}' AUSENTE")
    
    coverage = (found / len(contractual_patterns)) * 100
    print(f"\n   Cobertura: {found}/{len(contractual_patterns)} ({coverage:.0f}%)")
    assert coverage >= 75, f"Cobertura debería ser >= 75%, fue {coverage:.0f}%"


def test_comparacion_con_otras_categorias():
    """Compara configuración de riesgos con otras categorías similares."""
    print("\n✅ Test 7: Comparación con categorías similares")
    
    riesgos_terms = len(get_category_terms("riesgos"))
    causales_terms = len(get_category_terms("causales_rechazo"))
    garantias_terms = len(get_category_terms("garantias"))
    
    riesgos_top_k = get_category_top_k("riesgos")
    causales_top_k = get_category_top_k("causales_rechazo")
    
    print(f"   • Riesgos:  {riesgos_terms} términos, top_k={riesgos_top_k}")
    print(f"   • Causales: {causales_terms} términos, top_k={causales_top_k}")
    print(f"   • Garantías: {garantias_terms} términos")
    
    # Riesgos debería tener configuración similar a causales (ambas son críticas)
    assert riesgos_top_k == causales_top_k, "top_k debería ser igual que causales"
    assert riesgos_terms >= 20, f"Debe tener al menos 20 términos, tiene {riesgos_terms}"
    
    print(f"   ✓ Configuración coherente con categorías críticas")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE QUERY EXPANSION PARA RIESGOS")
    print("=" * 70)
    
    try:
        test_riesgos_glossary_cargado()
        test_query_terms_principales()
        test_aliases_expandidos()
        test_build_keyword_query_construye_string()
        test_top_k_configurado()
        test_cobertura_terminos_contractuales()
        test_comparacion_con_otras_categorias()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nQuery expansion para Riesgos funcionando correctamente:")
        print("  ✓ Términos principales cargados (multa, penalización, sanción, etc.)")
        print("  ✓ Aliases expandiendo cobertura (rescisión de contrato, etc.)")
        print("  ✓ Keyword query construida correctamente")
        print("  ✓ top_k=35 configurado (igual que causales)")
        print("  ✓ Cobertura de términos contractuales adecuada")
        print("\n  La búsqueda BM25 ahora recuperará fragmentos incluso con")
        print("  redacción variada (multa/penalización, rescisión/resolución, etc.)")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
