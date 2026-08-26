"""
Configuración de fixtures específicos para pruebas de timeline.

Sobrescribe el fixture setup_db para que NO se ejecute en pruebas de timeline
que no lo necesitan (como test_calculator.py que prueba funciones puras).

NOTA: Si en el futuro se agregan tests de timeline que SÍ necesiten DB
(como test_service.py), crear un conftest.py separado en un subdirectorio
o usar un marker pytest personalizado.
"""
import pytest


@pytest.fixture(autouse=True)
def setup_db():
    """
    Override del fixture global setup_db.
    
    Para pruebas de timeline que son funciones puras (calculator, models),
    no necesitamos setup de DB. Este fixture vacío evita que se ejecute
    el setup_db global.
    """
    yield
