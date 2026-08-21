#!/usr/bin/env python
"""Quick test for SubtipoRiesgo implementation."""

from analysis.extraction.schemas import RiesgoItem, SubtipoRiesgo, TipoRiesgo, SourceReference

print("Testing SubtipoRiesgo Implementation")
print("=" * 50)

# Test 1: Enum exists
print("✓ Test 1: SubtipoRiesgo enum imported successfully")

# Test 2: All subtypes exist
subtipos = [
    SubtipoRiesgo.EJECUCION,
    SubtipoRiesgo.INCUMPLIMIENTO,
    SubtipoRiesgo.OPERATIVO,
    SubtipoRiesgo.PLAZOS,
    SubtipoRiesgo.ECONOMICO,
    SubtipoRiesgo.TECNICO,
    SubtipoRiesgo.LEGAL_CONTRACTUAL,
    SubtipoRiesgo.OTRO_EXPLICITO,
]
assert len(subtipos) == 8
print("✓ Test 2: All 8 subtypes exist in enum")

# Test 3: Enum values are correct
assert SubtipoRiesgo.EJECUCION.value == "ejecucion"
assert SubtipoRiesgo.INCUMPLIMIENTO.value == "incumplimiento"
assert SubtipoRiesgo.OPERATIVO.value == "operativo"
assert SubtipoRiesgo.PLAZOS.value == "plazos"
assert SubtipoRiesgo.ECONOMICO.value == "economico"
assert SubtipoRiesgo.TECNICO.value == "tecnico"
assert SubtipoRiesgo.LEGAL_CONTRACTUAL.value == "legal_contractual"
assert SubtipoRiesgo.OTRO_EXPLICITO.value == "otro_explicito"
print("✓ Test 3: Enum values are correct")

# Test 4: RiesgoItem has subtipo field
source_ref = SourceReference(
    document_id="test-doc",
    page_number=5,
    citation="Riesgo de incumplimiento según cláusula 10"
)
item = RiesgoItem(
    tipo=TipoRiesgo.DESCALIFICACION,
    subtipo=SubtipoRiesgo.PLAZOS,
    valor="Riesgo de incumplimiento de plazo",
    confidence=0.9,
    extraction_status="success",
    source_references=[source_ref],
)
assert item.subtipo == SubtipoRiesgo.PLAZOS
assert item.subtipo.value == "plazos"
print("✓ Test 4: RiesgoItem accepts subtipo field")

# Test 5: Default subtipo is OTRO_EXPLICITO
item_default = RiesgoItem(
    tipo=TipoRiesgo.OTRO,
    valor="Riesgo sin clasificar",
    confidence=0.7,
    extraction_status="success",
    source_references=[source_ref],
)
assert item_default.subtipo == SubtipoRiesgo.OTRO_EXPLICITO
print("✓ Test 5: Default subtipo is OTRO_EXPLICITO")

# Test 6: All subtipos work with RiesgoItem
for subtipo in SubtipoRiesgo:
    item = RiesgoItem(
        tipo=TipoRiesgo.OTRO,
        subtipo=subtipo,
        valor=f"Test {subtipo.value}",
        confidence=0.8,
        extraction_status="success",
        source_references=[source_ref],
    )
    assert item.subtipo == subtipo
print("✓ Test 6: All subtipos work correctly in RiesgoItem")

# Test 7: Source references are preserved
item_amb = RiesgoItem(
    tipo=TipoRiesgo.OTRO,
    subtipo=SubtipoRiesgo.OTRO_EXPLICITO,
    valor="Riesgo ambiguo",
    confidence=0.6,
    extraction_status="success",
    source_references=[source_ref],
)
assert len(item_amb.source_references) == 1
assert item_amb.source_references[0].citation == "Riesgo de incumplimiento según cláusula 10"
print("✓ Test 7: Source references preserved for ambiguous risks")

print("=" * 50)
print("All tests PASSED ✓")
