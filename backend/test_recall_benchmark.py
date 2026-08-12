"""
Benchmark riguroso de Recall@K y Precision@K para validar retrieval híbrido.

OBJETIVO: 
No solo medir que recuperamos MÁS chunks, sino que recuperamos los CORRECTOS.

METODOLOGÍA:
1. Ground truth manual: marcar chunks relevantes esperados por categoría
2. Ejecutar retrieval con diferentes category_boost (0%, 10%, 15%, 20%, 25%)
3. Medir Recall@K, Precision@K, F1@K
4. Analizar distribución de categorías de origen
"""
import sys
import os
from pathlib import Path
from typing import Literal

# Fix encoding para Windows
if sys.platform == "win32":
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from analysis.extraction.extractors.base import _retrieve_with_category_priority
from shared.ports.azure_search import search_hybrid

ANALYSIS_ID = "ad2b40a4-3a83-4c51-b515-0563c0bb5a58"

# GROUND TRUTH MANUAL
# Chunks que DEBERÍAN ser recuperados para cada categoría
# (identificados por inspección manual del documento)
GROUND_TRUTH = {
    "causales_rechazo": {
        # Chunks que mencionan explícitamente rechazo/descalificación
        "expected_chunks": [
            # Página 2: "se rechazará la oferta del proponente"
            {"page": 2, "content_contains": "se rechazará la oferta"},
            # Página 3: "quedará desestimada su oferta"
            {"page": 3, "content_contains": "quedará desestimada"},
            # Página 4: "la municipalidad podrá rechazar todas las ofertas"
            {"page": 4, "content_contains": "podrá rechazar todas"},
            # Página 5: "quedará bajo exclusiva responsabilidad" (exclusión)
            {"page": 5, "content_contains": "exclusiva responsabilidad"},
            # Página 5: "no dando derecho" (exclusión de reclamo)
            {"page": 5, "content_contains": "no dando derecho"},
        ],
        "min_recall": 0.60,  # Al menos 60% de chunks esperados
    },
    "anexos_obligatorios": {
        "expected_chunks": [
            # Página 8: Anexo I - especificaciones técnicas
            {"page": 8, "content_contains": "anexo"},
            # Página 10: formularios/planillas
            {"page": 10, "content_contains": "formulario"},
        ],
        "min_recall": 0.50,
    },
    "requisitos_admisibilidad": {
        "expected_chunks": [
            # Página 2: documentación que acredite personería
            {"page": 2, "content_contains": "personería"},
            # Página 2: propuesta económica
            {"page": 2, "content_contains": "propuesta económica"},
            # Página 3: inscripción PAC
            {"page": 3, "content_contains": "padrón de agentes"},
        ],
        "min_recall": 0.60,
    },
}


def find_chunks_in_results(expected: list[dict], results: list[dict]) -> tuple[list, list]:
    """Identifica qué chunks esperados fueron recuperados."""
    found = []
    missing = []
    
    for exp in expected:
        page = exp["page"]
        content_pattern = exp["content_contains"].lower()
        
        matched = False
        for chunk in results:
            if (
                chunk["page_number"] == page
                and content_pattern in chunk["content"].lower()
            ):
                found.append(exp)
                matched = True
                break
        
        if not matched:
            missing.append(exp)
    
    return found, missing


def measure_recall_precision(
    category: str,
    query: str,
    keyword_query: str,
    top_k: int = 25,
    category_boost: float = 0.20,
) -> dict:
    """Mide Recall@K y Precision@K para una categoría."""
    
    if category not in GROUND_TRUTH:
        return {"error": f"No ground truth for {category}"}
    
    gt = GROUND_TRUTH[category]
    expected_chunks = gt["expected_chunks"]
    
    # Ejecutar retrieval
    results = _retrieve_with_category_priority(
        query=query,
        analysis_id=ANALYSIS_ID,
        top_k=top_k,
        keyword_query=keyword_query,
        category=category,
        correlation_id=f"benchmark_{category}",
        category_boost=category_boost,
    )
    
    # Identificar chunks encontrados vs perdidos
    found, missing = find_chunks_in_results(expected_chunks, results)
    
    # Recall: ¿cuántos de los esperados recuperamos?
    recall = len(found) / len(expected_chunks) if expected_chunks else 0.0
    
    # Analizar distribución de categorías
    category_dist = {}
    target_count = 0
    for chunk in results:
        primary = chunk.get("primary_category", "unknown")
        category_dist[primary] = category_dist.get(primary, 0) + 1
        
        if (
            primary == category
            or category in chunk.get("secondary_categories", [])
        ):
            target_count += 1
    
    # Precision aproximada: % de chunks con categoría target
    # (no es precision real porque no sabemos cuántos de los recuperados son irrelevantes)
    category_precision = target_count / len(results) if results else 0.0
    
    return {
        "category": category,
        "total_retrieved": len(results),
        "expected_chunks": len(expected_chunks),
        "found_chunks": len(found),
        "missing_chunks": len(missing),
        "recall": recall,
        "category_precision": category_precision,
        "category_distribution": category_dist,
        "found_details": found,
        "missing_details": missing,
        "meets_target": recall >= gt["min_recall"],
    }


def benchmark_category_boost_values():
    """Prueba diferentes valores de category_boost y mide impacto."""
    print("\n" + "="*80)
    print("BENCHMARK: Optimización de CATEGORY_BOOST")
    print("="*80)
    
    boost_values = [0.0, 0.10, 0.15, 0.20, 0.25]
    
    # Test solo con causales_rechazo (la más crítica)
    test_config = {
        "category": "causales_rechazo",
        "query": "Identificar causales de rechazo, descalificación o exclusión de ofertas",
        "keyword_query": "rechazo rechazada descalificacion inadmisibilidad exclusion desestimar",
    }
    
    print(f"\nCategoría de prueba: {test_config['category']}")
    print(f"Valores a probar: {[f'{b:.0%}' for b in boost_values]}")
    print(f"\n{'Boost':<10} {'Recall':<10} {'Cat Precision':<15} {'Target Met':<12}")
    print("─" * 50)
    
    results = []
    for boost in boost_values:
        metrics = measure_recall_precision(
            category=test_config['category'],
            query=test_config['query'],
            keyword_query=test_config['keyword_query'],
            category_boost=boost,
        )
        
        results.append((boost, metrics))
        
        target_indicator = "✅" if metrics['meets_target'] else "❌"
        print(
            f"{boost:>5.0%}     "
            f"{metrics['recall']:>6.1%}     "
            f"{metrics['category_precision']:>6.1%}          "
            f"{target_indicator}"
        )
    
    print("\n" + "─" * 50)
    print("\n🎯 RECOMENDACIÓN:")
    
    # Encontrar el boost óptimo: mayor recall sin sobreajustar
    optimal_boost = max(results, key=lambda x: x[1]['recall'])[0]
    print(f"   Boost óptimo: {optimal_boost:.0%}")
    print(f"   (maximiza recall sin perder diversidad de fuentes)")
    
    return results


def run_benchmark():
    """Ejecuta benchmark completo de Recall@K."""
    print("\n" + "="*80)
    print("🧪 BENCHMARK RIGUROSO: Recall@K y Precision@K")
    print("="*80)
    print(f"Documento: Pliego Licitacion Privada Servidores 2025")
    print(f"Analysis ID: {ANALYSIS_ID}")
    print(f"Top-K: 25")
    
    categories_to_test = [
        {
            "category": "causales_rechazo",
            "query": "Identificar causales de rechazo, descalificación o exclusión de ofertas",
            "keyword_query": "rechazo rechazada descalificacion inadmisibilidad exclusion desestimar",
        },
        {
            "category": "anexos_obligatorios",
            "query": "Identificar anexos, formularios y documentación obligatoria",
            "keyword_query": "anexo formulario planilla declaracion jurada",
        },
        {
            "category": "requisitos_admisibilidad",
            "query": "Identificar requisitos de admisibilidad y documentación exigida",
            "keyword_query": "requisitos admisibilidad documentacion personeria propuesta",
        },
    ]
    
    results = []
    for test in categories_to_test:
        print(f"\n{'─'*80}")
        print(f"CATEGORÍA: {test['category']}")
        print(f"{'─'*80}")
        
        metrics = measure_recall_precision(
            category=test["category"],
            query=test["query"],
            keyword_query=test["keyword_query"],
        )
        
        results.append(metrics)
        
        # Mostrar resultados
        print(f"\n📊 MÉTRICAS:")
        print(f"   Total recuperado: {metrics['total_retrieved']} chunks")
        print(f"   Esperados: {metrics['expected_chunks']} chunks")
        print(f"   Encontrados: {metrics['found_chunks']} chunks")
        print(f"   Perdidos: {metrics['missing_chunks']} chunks")
        print(f"\n   🎯 Recall@25: {metrics['recall']:.1%}")
        print(f"   📍 Category Precision: {metrics['category_precision']:.1%}")
        
        # Target
        target_met = "✅" if metrics['meets_target'] else "❌"
        min_recall = GROUND_TRUTH[test['category']]['min_recall']
        print(f"   {target_met} Target Recall (>= {min_recall:.0%}): {'MET' if metrics['meets_target'] else 'NOT MET'}")
        
        # Distribución
        print(f"\n📦 DISTRIBUCIÓN DE CATEGORÍAS:")
        for cat, count in sorted(
            metrics['category_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            bar = "█" * count
            marker = "→" if cat == test['category'] else " "
            print(f"   {marker} {cat:30s} {count:2d} {bar}")
        
        # Missing chunks
        if metrics['missing_details']:
            print(f"\n❌ CHUNKS PERDIDOS:")
            for miss in metrics['missing_details']:
                print(f"   P{miss['page']}: \"{miss['content_contains']}\"")
    
    # Resumen global
    print("\n" + "="*80)
    print("📊 RESUMEN GLOBAL")
    print("="*80)
    
    avg_recall = sum(r['recall'] for r in results) / len(results)
    all_met = all(r['meets_target'] for r in results)
    
    print(f"\nRecall promedio: {avg_recall:.1%}")
    print(f"Categorías que cumplen target: {sum(r['meets_target'] for r in results)}/{len(results)}")
    
    if all_met:
        print(f"\n✅ BENCHMARK EXITOSO")
        print(f"   Todas las categorías superan el recall mínimo")
        print(f"   ✓ Retrieval híbrido validado para producción")
    else:
        print(f"\n⚠️  BENCHMARK PARCIAL")
        failed = [r['category'] for r in results if not r['meets_target']]
        print(f"   Categorías bajo target: {', '.join(failed)}")
        print(f"   → Considerar ajustar category_boost o mejorar glossary")
    
    return results


if __name__ == "__main__":
    results = run_benchmark()
    benchmark_category_boost_values()
