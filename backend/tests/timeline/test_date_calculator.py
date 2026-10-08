"""
Tests para motor de cálculo determinístico de fechas.
"""
from datetime import date

import pytest

from timeline.date_calculator import add_business_days


class TestAddBusinessDaysCorridos:
    """Tests para cálculo de días corridos."""

    def test_add_corridos_basic(self):
        """AC1: Sumar días corridos básico - 45 días desde 2026-09-10 = 2026-10-25"""
        start = date(2026, 9, 10)  # Jueves
        result = add_business_days(start, 45, "corridos")
        expected = date(2026, 10, 25)
        assert result == expected

    def test_add_corridos_includes_weekends(self):
        """AC2: Días corridos incluyen fines de semana"""
        start = date(2026, 9, 10)  # Jueves
        result = add_business_days(start, 5, "corridos")
        expected = date(2026, 9, 15)  # Martes (incluye sábado 12 y domingo 13)
        assert result == expected

    def test_add_zero_days(self):
        """AC3: Días = 0 retorna fecha original"""
        start = date(2026, 9, 10)
        result = add_business_days(start, 0, "corridos")
        assert result == start

    def test_day_type_no_especificado_raises(self):
        """day_type='no_especificado' debe fallar con mensaje claro"""
        with pytest.raises(ValueError, match="no_especificado"):
            add_business_days(date(2026, 9, 10), 10, "no_especificado")

    def test_day_type_invalid_raises(self):
        """day_type inválido debe fallar"""
        with pytest.raises(ValueError, match="day_type inválido"):
            add_business_days(date(2026, 9, 10), 10, "invalido")

    def test_add_corridos_cross_month_boundary(self):
        """Días corridos cruzan límite de mes correctamente"""
        start = date(2026, 9, 28)  # Lunes
        result = add_business_days(start, 5, "corridos")
        expected = date(2026, 10, 3)  # Sábado (octubre)
        assert result == expected

    def test_add_corridos_cross_year_boundary(self):
        """Días corridos cruzan límite de año correctamente"""
        start = date(2026, 12, 25)  # Viernes
        result = add_business_days(start, 10, "corridos")
        expected = date(2027, 1, 4)  # Lunes 2027
        assert result == expected


class TestAddBusinessDaysHabiles:
    """Tests para días hábiles (implementados en story 17-2)."""

    def test_add_habiles_excludes_weekend(self):
        """AC1 y AC2: Días hábiles excluyen fin de semana"""
        start = date(2026, 9, 10)  # Jueves 10 sep
        result = add_business_days(start, 5, "hábiles")
        # Viernes 11 (1), Lunes 14 (2), Martes 15 (3), Miércoles 16 (4), Jueves 17 (5)
        expected = date(2026, 9, 17)
        assert result == expected

    def test_add_habiles_from_friday(self):
        """Días hábiles desde viernes"""
        start = date(2026, 9, 11)  # Viernes
        result = add_business_days(start, 3, "hábiles")
        # Lunes 14 (1), Martes 15 (2), Miércoles 16 (3)
        expected = date(2026, 9, 16)
        assert result == expected

    def test_add_habiles_zero_days(self):
        """Días hábiles con 0 días"""
        start = date(2026, 9, 10)
        result = add_business_days(start, 0, "hábiles")
        assert result == start

    def test_add_habiles_cross_multiple_weekends(self):
        """Días hábiles cruzan varios fines de semana"""
        start = date(2026, 9, 10)  # Jueves
        result = add_business_days(start, 10, "hábiles")
        # 10 días hábiles = 2 semanas (excluye 2 fines de semana)
        expected = date(2026, 9, 24)  # Jueves (14 días calendario)
        assert result == expected

    def test_habiles_logs_limitation(self, caplog):
        """AC3: Debe loguear que feriados no están implementados"""
        import logging
        # PATCH: Cambiado a DEBUG level
        with caplog.at_level(logging.DEBUG):
            add_business_days(date(2026, 9, 10), 5, "hábiles")
        assert "feriados NO implementados" in caplog.text or "AR4" in caplog.text
