"""
Test del schema de la categoría Riesgos.
Valida que RiesgoItem y ExtractedData cumplen el contrato definido en R3.1.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pydantic import ValidationError
from analysis.extraction.schemas import (
    RiesgoItem,
    TipoRiesgo,
    SubtipoRiesgo,
    ExtractedData,
    SourceReference
)


def test_riesgo_item_campos_obligatorios():
    """Verifica que RiesgoItem valida campos obligatorios (AC1)."""
    print("\n✅ Test 1: RiesgoItem - Campos obligatorios")
    
    # Item válido mínimo
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.PENALIZACION,
        subtipo=SubtipoRiesgo.ECONOMICO,
        valor="Multa del 10% por demora",
        extraction_status="success",
        confidence=0.9,
        source_references=[
            SourceReference(
                document_id="doc-123",
                page_number=5,
                citation="Se aplicará multa del 10% por cada día de demora"
            )
        ]
    )
    
    assert riesgo.tipo == TipoRiesgo.PENALIZACION
    assert riesgo.subtipo == SubtipoRiesgo.ECONOMICO
    assert riesgo.valor == "Multa del 10% por demora"
    assert len(riesgo.source_references) >= 1
    print("   ✓ Campos obligatorios validados")
    print(f"   ✓ tipo: {riesgo.tipo}, subtipo: {riesgo.subtipo}")


def test_riesgo_item_subtipo_default():
    """Verifica que subtipo tiene valor por defecto."""
    print("\n✅ Test 2: RiesgoItem - Subtipo con default")
    
    # Crear sin especificar subtipo
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.OTRO,
        valor="Algún riesgo sin subtipo específico",
        extraction_status="success",
        confidence=0.7,
        source_references=[
            SourceReference(
                document_id="doc-123",
                page_number=10,
                citation="Texto de evidencia"
            )
        ]
    )
    
    # Debe tener el valor por defecto
    assert riesgo.subtipo == SubtipoRiesgo.OTRO_EXPLICITO
    print(f"   ✓ Subtipo default aplicado: {riesgo.subtipo}")


def test_tipo_riesgo_enum_valores():
    """Verifica que TipoRiesgo tiene todos los valores esperados."""
    print("\n✅ Test 3: TipoRiesgo - Enum completo")
    
    expected_tipos = [
        "descalificacion",
        "penalizacion",
        "legal",
        "operativo",
        "financiero",
        "otro"
    ]
    
    for tipo_value in expected_tipos:
        tipo = TipoRiesgo(tipo_value)
        assert tipo.value == tipo_value
        print(f"   ✓ TipoRiesgo.{tipo.name} = '{tipo.value}'")


def test_subtipo_riesgo_enum_valores():
    """Verifica que SubtipoRiesgo tiene todos los valores esperados."""
    print("\n✅ Test 4: SubtipoRiesgo - Enum completo")
    
    expected_subtipos = [
        "ejecucion",
        "incumplimiento",
        "operativo",
        "plazos",
        "economico",
        "tecnico",
        "legal_contractual",
        "otro_explicito"
    ]
    
    for subtipo_value in expected_subtipos:
        subtipo = SubtipoRiesgo(subtipo_value)
        assert subtipo.value == subtipo_value
        print(f"   ✓ SubtipoRiesgo.{subtipo.name} = '{subtipo.value}'")


def test_extracted_data_campos_riesgos():
    """Verifica que ExtractedData tiene los campos de riesgos (AC1, AC2)."""
    print("\n✅ Test 5: ExtractedData - Campos de riesgos")
    
    # ExtractedData con riesgos
    data = ExtractedData(
        riesgos=[
            RiesgoItem(
                tipo=TipoRiesgo.FINANCIERO,
                subtipo=SubtipoRiesgo.ECONOMICO,
                valor="Multa por incumplimiento",
                extraction_status="success",
                confidence=0.95,
                source_references=[
                    SourceReference(
                        document_id="doc-1",
                        page_number=8,
                        citation="Multa del 5% por cada día de atraso"
                    )
                ]
            )
        ],
        riesgos_extraction_status="success"
    )
    
    assert hasattr(data, "riesgos")
    assert hasattr(data, "riesgos_extraction_status")
    assert hasattr(data, "riesgos_narrative")
    assert len(data.riesgos) == 1
    assert data.riesgos_extraction_status == "success"
    print("   ✓ Campo 'riesgos' presente y funcional")
    print("   ✓ Campo 'riesgos_extraction_status' presente")
    print("   ✓ Campo 'riesgos_narrative' presente")


def test_extracted_data_sin_riesgos():
    """Verifica que ExtractedData funciona sin riesgos (AC2)."""
    print("\n✅ Test 6: ExtractedData - Sin riesgos (AC2)")
    
    # ExtractedData sin riesgos
    data = ExtractedData(
        riesgos=[],
        riesgos_extraction_status="not_found"
    )
    
    assert len(data.riesgos) == 0
    assert data.riesgos_extraction_status == "not_found"
    assert data.riesgos_narrative is None
    print("   ✓ Lista vacía aceptada")
    print("   ✓ Status 'not_found' válido")
    print("   ✓ Narrative None por defecto")


def test_riesgo_item_source_references_min_1():
    """Verifica que source_references requiere al menos 1 item para ítems válidos."""
    print("\n✅ Test 7: RiesgoItem - Source references mínimo 1")
    
    # Debe fallar sin source_references
    try:
        riesgo = RiesgoItem(
            tipo=TipoRiesgo.LEGAL,
            subtipo=SubtipoRiesgo.LEGAL_CONTRACTUAL,
            valor="Riesgo sin fuentes",
            extraction_status="success",
            confidence=0.8,
            source_references=[]  # Vacío - debería fallar
        )
        # Si llegamos acá, el test falla
        assert False, "Debería fallar con source_references vacío"
    except ValidationError as e:
        print("   ✓ Validación correcta: rechaza source_references vacío")
        print(f"   ✓ Error esperado: {str(e)[:100]}...")


def test_riesgo_item_metadata_opcional():
    """Verifica que metadata es opcional y tiene default."""
    print("\n✅ Test 8: RiesgoItem - Metadata opcional")
    
    # Sin metadata explícito
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.OPERATIVO,
        subtipo=SubtipoRiesgo.OPERATIVO,
        valor="Riesgo operativo",
        extraction_status="success",
        confidence=0.85,
        source_references=[
            SourceReference(
                document_id="doc-1",
                page_number=3,
                citation="Evidencia del riesgo operativo"
            )
        ]
    )
    
    assert hasattr(riesgo, "metadata")
    assert isinstance(riesgo.metadata, dict)
    assert len(riesgo.metadata) == 0
    print("   ✓ metadata es opcional")
    print("   ✓ Default es diccionario vacío")


def test_riesgo_item_serializacion():
    """Verifica que RiesgoItem se serializa correctamente."""
    print("\n✅ Test 9: RiesgoItem - Serialización")
    
    riesgo = RiesgoItem(
        tipo=TipoRiesgo.PENALIZACION,
        subtipo=SubtipoRiesgo.INCUMPLIMIENTO,
        valor="Rescisión por incumplimiento grave",
        extraction_status="success",
        confidence=0.92,
        source_references=[
            SourceReference(
                document_id="doc-xyz",
                page_number=12,
                citation="El contrato podrá rescindirse en caso de incumplimiento grave"
            )
        ],
        metadata={"severidad": "alta"}
    )
    
    # Serializar a dict
    riesgo_dict = riesgo.model_dump()
    
    assert riesgo_dict["tipo"] == "penalizacion"  # Valor del enum, no el nombre
    assert riesgo_dict["subtipo"] == "incumplimiento"
    assert riesgo_dict["valor"] == "Rescisión por incumplimiento grave"
    assert len(riesgo_dict["source_references"]) == 1
    assert riesgo_dict["metadata"]["severidad"] == "alta"
    print("   ✓ Serialización a dict correcta")
    print(f"   ✓ Enums serializados como strings")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE SCHEMA DE CATEGORÍA RIESGOS")
    print("=" * 70)
    
    try:
        test_riesgo_item_campos_obligatorios()
        test_riesgo_item_subtipo_default()
        test_tipo_riesgo_enum_valores()
        test_subtipo_riesgo_enum_valores()
        test_extracted_data_campos_riesgos()
        test_extracted_data_sin_riesgos()
        test_riesgo_item_source_references_min_1()
        test_riesgo_item_metadata_opcional()
        test_riesgo_item_serializacion()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nEl schema de Riesgos cumple todos los criterios:")
        print("  ✓ AC1: Cada item cumple campos obligatorios")
        print("  ✓ AC2: Contrato válido con y sin hallazgos")
        print("\nDetalles del schema:")
        print("  • RiesgoItem con tipo, subtipo, valor, metadata")
        print("  • 6 valores de TipoRiesgo")
        print("  • 8 valores de SubtipoRiesgo")
        print("  • Subtipo con default OTRO_EXPLICITO")
        print("  • ExtractedData con riesgos, status, narrative")
        print("  • source_references mínimo 1 (validado)")
        print("  • Serialización correcta de enums")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
