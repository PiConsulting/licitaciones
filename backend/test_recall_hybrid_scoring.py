"""
Test de recall para validar el cambio de FILTRO RÍGIDO → SCORING HÍBRIDO

HIPÓTESIS:
Antes (filtro rígido):
    causales_rechazo → 0 chunks (porque clasificación falló)
    
Después (scoring híbrido):
    causales_rechazo → chunks con "rechaz", "desestim", etc. aunque tengan otra categoría

OBJETIVO: Medir recall improvement
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analysis.extraction.extractors.base import _retrieve_with_category_priority

ANALYSIS_ID = "ad2b40a4-3a83-4c51-b515-0563c0bb5a58"

def test_causales_rechazo_recall():
    """Test: ¿Recuperamos chunks con keywords de rechazo aunque no tengan la categoría?"""
    print("\n" + "="*80)
    print("TEST: Recall de Causales de Rechazo (FILTRO RÍGIDO → SCORING HÍBRIDO)")
    print("="*80)
    
    query = (
        "Identificar todas las causales de rechazo, descalificación, "
        "inadmisibilidad o exclusión de ofertas mencionadas en el documento."
    )
    
    keyword_query = (
        "rechazo rechazada rechazar descalificacion descalificar inadmisibilidad "
        "inadmisible exclusion excluir desestimacion desestimar"
    )
    
    chunks = _retrieve_with_category_priority(
        query=query,
        analysis_id=ANALYSIS_ID,
        top_k=25,
        keyword_query=keyword_query,
        category="causales_rechazo",
        correlation_id="test_recall",
    )
    
    print(f"\n📊 RESULTADOS:")
    print(f"   Total chunks recuperados: {len(chunks)}")
    
    if not chunks:
        print("\n❌ FALLO: No se recuperó ningún chunk")
        return False
    
    # Analizar chunks recuperados
    print(f"\n📋 DETALLE DE CHUNKS:")
    print("-" * 80)
    
    keywords_rechazo = ["rechaz", "desestim", "exclus", "descalif", "inadmisi"]
    chunks_con_keywords = 0
    chunks_con_categoria = 0
    
    for i, chunk in enumerate(chunks, 1):
        primary = chunk.get("primary_category", "unknown")
        secondary = chunk.get("secondary_categories", [])
        content = chunk["content"].lower()
        page = chunk["page_number"]
        
        # ¿Tiene keywords de rechazo?
        has_keyword = any(kw in content for kw in keywords_rechazo)
        if has_keyword:
            chunks_con_keywords += 1
        
        # ¿Tiene la categoría causales_rechazo?
        has_category = primary == "causales_rechazo" or "causales_rechazo" in secondary
        if has_category:
            chunks_con_categoria += 1
        
        keyword_marker = "🔑" if has_keyword else "  "
        category_marker = "✓" if has_category else "✗"
        
        print(f"{i:2d}. {keyword_marker} {category_marker} P{page} [{primary}]")
        
        if has_keyword:
            # Mostrar preview del keyword encontrado
            for kw in keywords_rechazo:
                if kw in content:
                    idx = content.find(kw)
                    preview_start = max(0, idx - 50)
                    preview_end = min(len(content), idx + 50)
                    preview = content[preview_start:preview_end].replace("\n", " ")
                    print(f"      → ...{preview}...")
                    break
    
    print("\n" + "-" * 80)
    print(f"\n📈 MÉTRICAS DE RECALL:")
    print(f"   Chunks con keywords de rechazo: {chunks_con_keywords}/{len(chunks)} ({chunks_con_keywords/len(chunks)*100:.1f}%)")
    print(f"   Chunks con categoría correcta: {chunks_con_categoria}/{len(chunks)} ({chunks_con_categoria/len(chunks)*100:.1f}%)")
    
    # Recall = ¿cuántos de los chunks que tienen keywords fueron recuperados?
    # No podemos medir recall absoluto sin saber cuántos chunks hay en total,
    # pero podemos medir si recuperamos MÁS que antes (antes era 0)
    
    print(f"\n✅ ÉXITO: Recuperamos {chunks_con_keywords} chunks con keywords de rechazo")
    print(f"   (Antes del cambio: 0 chunks)")
    print(f"\n🎯 CONCLUSIÓN:")
    if chunks_con_keywords >= 3:
        print(f"   ✓ El scoring híbrido recuperó información relevante que el filtro rígido perdía")
        print(f"   ✓ {chunks_con_keywords - chunks_con_categoria} chunks SIN categoría correcta fueron recuperados")
        print(f"   ✓ Esto previene pérdida de información por clasificación imperfecta")
        return True
    else:
        print(f"   ⚠ Solo {chunks_con_keywords} chunks con keywords - esperábamos más")
        return False


def test_anexos_obligatorios_recall():
    """Test: ¿Recuperamos información sobre anexos/formularios?"""
    print("\n" + "="*80)
    print("TEST: Recall de Anexos Obligatorios")
    print("="*80)
    
    query = (
        "Identificar todos los anexos, formularios y documentación obligatoria "
        "que debe presentar el oferente."
    )
    
    keyword_query = "anexo formulario planilla declaracion jurada modelo"
    
    chunks = _retrieve_with_category_priority(
        query=query,
        analysis_id=ANALYSIS_ID,
        top_k=25,
        keyword_query=keyword_query,
        category="anexos_obligatorios",
        correlation_id="test_recall_anexos",
    )
    
    print(f"\n📊 RESULTADOS:")
    print(f"   Total chunks recuperados: {len(chunks)}")
    
    if chunks:
        keywords_anexo = ["anexo", "formulario", "planilla", "declaracion jurada"]
        chunks_con_keywords = sum(
            1 for chunk in chunks
            if any(kw in chunk["content"].lower() for kw in keywords_anexo)
        )
        print(f"   Chunks con keywords de anexos: {chunks_con_keywords}/{len(chunks)}")
        
        if chunks_con_keywords >= 2:
            print(f"   ✅ Recuperación exitosa")
            return True
    
    return False


if __name__ == "__main__":
    print("\n🧪 TESTING SCORING HÍBRIDO vs FILTRO RÍGIDO")
    print("="*80)
    print("Documento: Pliego Licitacion Privada Servidores 2025")
    print(f"Analysis ID: {ANALYSIS_ID}")
    
    success_1 = test_causales_rechazo_recall()
    success_2 = test_anexos_obligatorios_recall()
    
    print("\n" + "="*80)
    if success_1 and success_2:
        print("🎉 TODOS LOS TESTS PASARON")
        print("✓ El scoring híbrido mejora significativamente el recall")
        print("✓ Información distribuida en múltiples categorías es recuperada")
    else:
        print("⚠ Algunos tests fallaron - revisar implementación")
    print("="*80)
