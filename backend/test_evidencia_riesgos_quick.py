"""
Test de evidencia por item de riesgo.
Valida que cada riesgo conserva sus source_references a través del pipeline completo.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from analysis.extraction.schemas import (
    RiesgoItem,
    TipoRiesgo,
    SubtipoRiesgo,
    SourceReference,
    ExtractedData
)


def test_riesgo_item_conserva_evidencia():
    """Verifica que RiesgoItem conserva source_references (AC1)."""
    print("\n✅ Test 1: RiesgoItem conserva evidencia")
    
    # Crear riesgo con evidencia
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.PENALIZACION,
        subtipo=SubtipoRiesgo.ECONOMICO,
        valor="Multa del 10% por cada día de demora",
        extraction_status="success",
        confidence=0.95,
        source_references=[
            SourceReference(
                document_id="doc-123",
                page_number=15,
                citation="Se aplicará una multa equivalente al 10% del valor total del contrato por cada día de demora"
            )
        ]
    )
    
    # Verificar que la evidencia se conserva
    assert len(riesgo.source_references) == 1
    assert riesgo.source_references[0].document_id == "doc-123"
    assert riesgo.source_references[0].page_number == 15
    assert "10%" in riesgo.source_references[0].citation
    
    print(f"   ✓ document_id conservado: {riesgo.source_references[0].document_id}")
    print(f"   ✓ page_number conservado: {riesgo.source_references[0].page_number}")
    print(f"   ✓ citation conservada ({len(riesgo.source_references[0].citation)} caracteres)")


def test_multiple_source_references():
    """Verifica que un riesgo puede tener múltiples fuentes."""
    print("\n✅ Test 2: Múltiples source_references por riesgo")
    
    # Riesgo mencionado en varias páginas
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.LEGAL,
        subtipo=SubtipoRiesgo.LEGAL_CONTRACTUAL,
        valor="Rescisión del contrato por incumplimiento grave",
        extraction_status="success",
        confidence=0.90,
        source_references=[
            SourceReference(
                document_id="doc-123",
                page_number=10,
                citation="El contrato podrá rescindirse de pleno derecho ante incumplimiento grave"
            ),
            SourceReference(
                document_id="doc-123",
                page_number=25,
                citation="Se considerará incumplimiento grave la falta de entrega en el plazo estipulado"
            ),
        ]
    )
    
    assert len(riesgo.source_references) == 2
    assert all(ref.document_id == "doc-123" for ref in riesgo.source_references)
    assert riesgo.source_references[0].page_number == 10
    assert riesgo.source_references[1].page_number == 25
    
    print(f"   ✓ {len(riesgo.source_references)} fuentes conservadas")
    print(f"   ✓ Páginas: {[ref.page_number for ref in riesgo.source_references]}")


def test_evidencia_accesible_en_extracted_data():
    """Verifica que la evidencia está accesible en ExtractedData (AC2)."""
    print("\n✅ Test 3: Evidencia accesible en ExtractedData (AC2)")
    
    # Crear múltiples riesgos con evidencia
    riesgos = [
        RiesgoItem(
            tipo=TipoRiesgo.FINANCIERO,
            subtipo=SubtipoRiesgo.ECONOMICO,
            valor="Multa diaria del 0.5%",
            extraction_status="success",
            confidence=0.92,
            source_references=[
                SourceReference(
                    document_id="doc-abc",
                    page_number=8,
                    citation="Multa diaria del 0.5% del valor del contrato"
                )
            ]
        ),
        RiesgoItem(
            tipo=TipoRiesgo.OPERATIVO,
            subtipo=SubtipoRiesgo.PLAZOS,
            valor="Penalización por entrega tardía",
            extraction_status="success",
            confidence=0.88,
            source_references=[
                SourceReference(
                    document_id="doc-abc",
                    page_number=12,
                    citation="Penalización por demora en la entrega de equipos"
                ),
                SourceReference(
                    document_id="doc-abc",
                    page_number=13,
                    citation="La penalización será del 1% por semana de atraso"
                ),
            ]
        ),
    ]
    
    # Crear ExtractedData
    data = ExtractedData(
        riesgos=riesgos,
        riesgos_extraction_status="success"
    )
    
    # Verificar que todos los riesgos tienen evidencia
    assert len(data.riesgos) == 2
    assert all(len(r.source_references) >= 1 for r in data.riesgos)
    
    # Verificar evidencia del primer riesgo
    primer_riesgo = data.riesgos[0]
    assert len(primer_riesgo.source_references) == 1
    assert primer_riesgo.source_references[0].document_id == "doc-abc"
    assert primer_riesgo.source_references[0].page_number == 8
    
    # Verificar evidencia del segundo riesgo (múltiples fuentes)
    segundo_riesgo = data.riesgos[1]
    assert len(segundo_riesgo.source_references) == 2
    assert segundo_riesgo.source_references[0].page_number == 12
    assert segundo_riesgo.source_references[1].page_number == 13
    
    print(f"   ✓ {len(data.riesgos)} riesgos con evidencia")
    print(f"   ✓ Primer riesgo: {len(primer_riesgo.source_references)} fuente(s)")
    print(f"   ✓ Segundo riesgo: {len(segundo_riesgo.source_references)} fuente(s)")


def test_evidencia_serializada_json():
    """Verifica que la evidencia se serializa correctamente para el frontend."""
    print("\n✅ Test 4: Evidencia serializada a JSON")
    
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.DESCALIFICACION,
        subtipo=SubtipoRiesgo.INCUMPLIMIENTO,
        valor="Descalificación por presentación extemporánea",
        extraction_status="success",
        confidence=0.97,
        source_references=[
            SourceReference(
                document_id="doc-xyz-789",
                page_number=3,
                citation="Las ofertas presentadas fuera del plazo establecido serán rechazadas de pleno derecho"
            )
        ]
    )
    
    # Serializar a dict (como lo haría la API)
    riesgo_dict = riesgo.model_dump()
    
    # Verificar estructura JSON
    assert "source_references" in riesgo_dict
    assert isinstance(riesgo_dict["source_references"], list)
    assert len(riesgo_dict["source_references"]) == 1
    
    # Verificar campos de evidencia
    evidencia = riesgo_dict["source_references"][0]
    assert evidencia["document_id"] == "doc-xyz-789"
    assert evidencia["page_number"] == 3
    assert "presentadas fuera del plazo" in evidencia["citation"]
    
    print("   ✓ source_references serializado como lista")
    print(f"   ✓ Campos de evidencia completos: document_id, page_number, citation")
    print(f"   ✓ JSON listo para consumo del frontend")


def test_evidencia_con_campos_opcionales():
    """Verifica que source_references acepta campos opcionales (filename, is_primary)."""
    print("\n✅ Test 5: Campos opcionales en source_references")
    
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.OPERATIVO,
        subtipo=SubtipoRiesgo.TECNICO,
        valor="Requisito técnico incumplible",
        extraction_status="success",
        confidence=0.85,
        source_references=[
            SourceReference(
                document_id="doc-456",
                page_number=20,
                citation="Especificación técnica incompatible con el mercado actual",
                filename="Pliego_Tecnico.pdf",
                is_primary=True
            )
        ]
    )
    
    # Verificar campos opcionales
    ref = riesgo.source_references[0]
    assert hasattr(ref, "filename")
    assert hasattr(ref, "is_primary")
    
    if ref.filename:
        print(f"   ✓ filename conservado: {ref.filename}")
    if hasattr(ref, "is_primary"):
        print(f"   ✓ is_primary conservado: {ref.is_primary}")
    
    # Serializar
    riesgo_dict = riesgo.model_dump()
    evidencia = riesgo_dict["source_references"][0]
    
    if "filename" in evidencia:
        assert evidencia["filename"] == "Pliego_Tecnico.pdf"
    if "is_primary" in evidencia:
        assert evidencia["is_primary"] == True
    
    print("   ✓ Campos opcionales serializados correctamente")


def test_no_acepta_riesgo_sin_evidencia():
    """Verifica que no se acepta riesgo sin source_references (regla anti-invención)."""
    print("\n✅ Test 6: Rechazo de riesgo sin evidencia")
    
    from pydantic import ValidationError
    
    try:
        riesgo = RiesgoItem(
            tipo=TipoRiesgo.OTRO,
            subtipo=SubtipoRiesgo.OTRO_EXPLICITO,
            valor="Riesgo inventado sin evidencia",
            extraction_status="success",
            confidence=0.7,
            source_references=[]  # SIN EVIDENCIA
        )
        assert False, "Debería rechazar riesgo sin evidencia"
    except ValidationError:
        print("   ✓ Validación correcta: rechaza riesgo sin source_references")
        print("   ✓ Regla anti-invención enforced")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE EVIDENCIA POR ITEM DE RIESGO")
    print("=" * 70)
    
    try:
        test_riesgo_item_conserva_evidencia()
        test_multiple_source_references()
        test_evidencia_accesible_en_extracted_data()
        test_evidencia_serializada_json()
        test_evidencia_con_campos_opcionales()
        test_no_acepta_riesgo_sin_evidencia()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nLa evidencia por item de riesgo funciona correctamente:")
        print("  ✓ AC1: document_id, page_number, citation se conservan")
        print("  ✓ AC2: Evidencia accesible en ExtractedData para frontend")
        print("\nCaracterísticas validadas:")
        print("  • source_references obligatorio (min 1)")
        print("  • Múltiples fuentes por riesgo soportadas")
        print("  • Campos opcionales (filename, is_primary) funcionan")
        print("  • Serialización JSON correcta")
        print("  • Regla anti-invención enforced (sin evidencia = rechazado)")
        print("\n  El frontend puede navegar a cada fuente con:")
        print("  • document_id para identificar el documento")
        print("  • page_number para posicionar el visor PDF")
        print("  • citation para resaltar el texto")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
