#!/usr/bin/env python
"""Test normalization of riesgo subtipos."""

import sys
sys.path.insert(0, "C:\\Users\\AgostinaTorres\\Desktop\\Proyectos\\licitaciones\\licitaciones-pi\\backend")

from analysis.extraction.graph import _canonical_riesgo_subtipo

print("Testing _canonical_riesgo_subtipo normalization")
print("=" * 50)

tests = [
    ("ejecucion del contrato", "ejecucion"),
    ("ejecutar el servicio", "ejecucion"),
    ("incumplimiento de obligaciones", "incumplimiento"),
    ("falta de entrega", "incumplimiento"),
    ("plazo de entrega", "plazos"),
    ("demora en la ejecución", "plazos"),
    ("multa economica", "economico"),
    ("sanción monetaria", "economico"),
    ("penalización financiera", "economico"),
    ("especificacion tecnica", "tecnico"),
    ("norma de calidad", "tecnico"),
    ("clausula legal", "legal_contractual"),
    ("rescisión contractual", "legal_contractual"),
    ("gestion operativa", "operativo"),
    ("logística del proyecto", "operativo"),
    ("riesgo ambiguo", "otro_explicito"),
    ("situación no especificada", "otro_explicito"),
    ("", "otro_explicito"),
]

passed = 0
failed = 0

for input_val, expected in tests:
    result = _canonical_riesgo_subtipo(input_val)
    if result == expected:
        print(f"✓ '{input_val}' -> {result}")
        passed += 1
    else:
        print(f"✗ '{input_val}' -> {result} (expected: {expected})")
        failed += 1

print("=" * 50)
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("All normalization tests PASSED ✓")
else:
    print(f"FAILED: {failed} test(s) did not pass")
    sys.exit(1)
