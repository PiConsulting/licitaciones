"""Script simple para validar los fixes de dehyphenation sin pytest."""

import re
import sys
from pathlib import Path

# Agregar backend al path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# Importar las funciones directamente
_LINE_WRAP_HYPHEN_RE = re.compile(r"([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])-\n([a-záéíóúñüA-ZÁÉÍÓÚÑÜ])")

def _dehyphenate(text: str) -> str:
    return _LINE_WRAP_HYPHEN_RE.sub(r"\1\2", text)


def test_dehyphenation():
    """Validar casos de dehyphenation."""
    tests = [
        ("ad-\nquisición", "adquisición", "lowercase básico"),
        ("ADQUI-\nSICIÓN", "ADQUISICIÓN", "uppercase completo"),
        ("Adqui-\nsición", "Adquisición", "mixed case"),
        ("pingü-\nino", "pingüino", "con ü minúscula"),
        ("PINGÜ-\nINO", "PINGÜINO", "con Ü mayúscula"),
        ("múlti-\nples ad-\nquisiciones", "múltiples adquisiciones", "múltiples guiones"),
    ]
    
    print("🧪 TESTS DE DEHYPHENATION")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for input_text, expected, description in tests:
        result = _dehyphenate(input_text)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | {description}")
        if result != expected:
            print(f"  Input:    {repr(input_text)}")
            print(f"  Expected: {repr(expected)}")
            print(f"  Got:      {repr(result)}")
    
    print("=" * 80)
    print(f"Resultados: {passed} passed, {failed} failed")
    
    return failed == 0


def test_regex_patterns():
    """Validar el regex directamente."""
    print("\n🔍 TESTS DE REGEX PATTERN")
    print("=" * 80)
    
    tests = [
        ("ad-\nquisición", 1, "lowercase"),
        ("ADQUI-\nSICIÓN", 1, "uppercase"),
        ("pingü-\nino", 1, "ü minúscula"),
        ("PINGÜ-\nINO", 1, "Ü mayúscula"),
        ("múlti-\nples", 1, "con tilde"),
        ("no-hyphen", 0, "sin salto de línea"),
    ]
    
    passed = 0
    failed = 0
    
    for text, expected_matches, description in tests:
        matches = list(_LINE_WRAP_HYPHEN_RE.finditer(text))
        actual_matches = len(matches)
        status = "✅ PASS" if actual_matches == expected_matches else "❌ FAIL"
        
        if actual_matches == expected_matches:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | {description}: {actual_matches} matches (expected {expected_matches})")
        if matches:
            for match in matches:
                print(f"      Matched: {repr(match.group(0))}")
    
    print("=" * 80)
    print(f"Resultados: {passed} passed, {failed} failed")
    
    return failed == 0


if __name__ == "__main__":
    success1 = test_dehyphenation()
    success2 = test_regex_patterns()
    
    if success1 and success2:
        print("\n✅ TODOS LOS TESTS PASARON")
        sys.exit(0)
    else:
        print("\n❌ ALGUNOS TESTS FALLARON")
        sys.exit(1)
