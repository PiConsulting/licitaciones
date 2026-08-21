#!/usr/bin/env python
"""Simple test to verify riesgos implementation."""

from analysis.extraction.schemas import RiesgoItem, TipoRiesgo, ExtractedData, SourceReference
from analysis.extraction.extractors import extractor_riesgos

print("Testing Riesgos Implementation")
print("=" * 50)

# Test 1: Imports work
print("✓ Test 1: Imports successful")

# Test 2: ExtractedData has riesgos fields
data = ExtractedData()
assert hasattr(data, "riesgos"), "ExtractedData missing riesgos field"
assert hasattr(data, "riesgos_extraction_status"), "ExtractedData missing riesgos_extraction_status"
assert hasattr(data, "riesgos_narrative"), "ExtractedData missing riesgos_narrative"
assert isinstance(data.riesgos, list), "riesgos should be a list"
assert data.riesgos_extraction_status == "unknown", "Initial status should be 'unknown'"
print("✓ Test 2: ExtractedData schema includes riesgos fields")

# Test 3: RiesgoItem can be created
source_ref = SourceReference(
    document_id="test-doc-123",
    page_number=5,
    citation="Riesgo de descalificación por documentación incompleta según art. 10"
)
item = RiesgoItem(
    tipo=TipoRiesgo.DESCALIFICACION,
    valor="Riesgo de descalificación por documentación incompleta",
    confidence=0.95,
    extraction_status="success",
    source_references=[source_ref],
)
assert item.tipo == TipoRiesgo.DESCALIFICACION, "Tipo mismatch"
assert "descalificación" in item.valor, "Valor incorrect"
assert item.confidence == 0.95, "Confidence incorrect"
print("✓ Test 3: RiesgoItem can be created with required fields")

# Test 4: All TipoRiesgo values work
for tipo in TipoRiesgo:
    item = RiesgoItem(
        tipo=tipo,
        valor=f"Test {tipo.value}",
        confidence=0.9,
        extraction_status="success",
        source_references=[source_ref],
    )
    assert item.tipo == tipo
print("✓ Test 4: All TipoRiesgo enum values work")

# Test 5: Extractor callable
assert callable(extractor_riesgos), "extractor_riesgos should be callable"
print("✓ Test 5: Extractor is callable")

print("=" * 50)
print("All tests PASSED ✓")
