"""
Test de exportación de tipos de Riesgos desde schemas.py.
Verifica que RiesgoItem, TipoRiesgo y SubtipoRiesgo están en __all__.
"""

import sys
from pathlib import Path

# Asegurar que el backend esté en el path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def test_exports_riesgos():
    """Verifica que los tipos de Riesgos se pueden importar."""
    print("\n✅ Test: Exportación de tipos de Riesgos")
    
    # Import directo
    from analysis.extraction.schemas import (
        RiesgoItem,
        TipoRiesgo,
        SubtipoRiesgo
    )
    
    print("   ✓ RiesgoItem importado correctamente")
    print("   ✓ TipoRiesgo importado correctamente")
    print("   ✓ SubtipoRiesgo importado correctamente")
    
    # Verificar que son los tipos correctos
    assert hasattr(RiesgoItem, 'model_fields')
    assert hasattr(TipoRiesgo, 'PENALIZACION')
    assert hasattr(SubtipoRiesgo, 'ECONOMICO')
    
    print("   ✓ Tipos válidos y completos")


def test_wildcard_import():
    """Verifica que import * funciona."""
    print("\n✅ Test: Import wildcard")
    
    # Crear namespace limpio
    namespace = {}
    
    # Import *
    exec("from analysis.extraction.schemas import *", namespace)
    
    # Verificar que los tipos están disponibles
    assert 'RiesgoItem' in namespace
    assert 'TipoRiesgo' in namespace
    assert 'SubtipoRiesgo' in namespace
    
    print("   ✓ RiesgoItem disponible con import *")
    print("   ✓ TipoRiesgo disponible con import *")
    print("   ✓ SubtipoRiesgo disponible con import *")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTS DE EXPORTACIÓN DE TIPOS RIESGOS")
    print("=" * 70)
    
    try:
        test_exports_riesgos()
        test_wildcard_import()
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        print("\nTipos de Riesgos correctamente exportados:")
        print("  ✓ RiesgoItem en __all__")
        print("  ✓ TipoRiesgo en __all__")
        print("  ✓ SubtipoRiesgo en __all__")
        print("  ✓ Import directo funciona")
        print("  ✓ Import wildcard funciona")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
