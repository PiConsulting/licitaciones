"""
Pruebas para el motor de cálculo determinístico de fechas (Épica 17).

Tests para:
- Cálculo de días corridos (17-1)
- Cálculo de días hábiles (17-2)
- Motor de recálculo en cascada (17-3)
- Validación de plazos antes del cálculo (17-4)

Estas pruebas no requieren DB, solo prueban funciones puras de cálculo.
"""
from datetime import date, timedelta
import pytest

from timeline.calculator import (
    calcular_dias_corridos,
    calcular_dias_habiles,
    calcular_fechas_cascada,
    validar_plazo_antes_calculo,
    ValidationError,
    CircularDependencyError,
)
from timeline.models import Event, Deadline


class TestCalculoDiasCorridos:
    """Pruebas para cálculo de días corridos (17-1)."""
    
    def test_suma_dias_corridos_positivos(self):
        """Suma días corridos hacia adelante."""
        fecha_base = date(2026, 1, 15)  # Miércoles
        resultado = calcular_dias_corridos(fecha_base, 10, "desde")
        assert resultado == date(2026, 1, 25)  # 10 días después
    
    def test_suma_dias_corridos_atraviesa_mes(self):
        """Días corridos cruzan límite de mes."""
        fecha_base = date(2026, 1, 28)
        resultado = calcular_dias_corridos(fecha_base, 5, "desde")
        assert resultado == date(2026, 2, 2)  # Cruza a febrero
    
    def test_suma_dias_corridos_atraviesa_anio(self):
        """Días corridos cruzan límite de año."""
        fecha_base = date(2025, 12, 28)
        resultado = calcular_dias_corridos(fecha_base, 10, "desde")
        assert resultado == date(2026, 1, 7)  # Cruza a 2026
    
    def test_resta_dias_corridos_antes_de(self):
        """Resta días corridos hacia atrás (antes_de)."""
        fecha_base = date(2026, 1, 15)
        resultado = calcular_dias_corridos(fecha_base, 10, "antes_de")
        assert resultado == date(2026, 1, 5)  # 10 días antes
    
    def test_cero_dias_corridos_retorna_misma_fecha(self):
        """Cero días retorna la fecha base sin cambios."""
        fecha_base = date(2026, 1, 15)
        resultado = calcular_dias_corridos(fecha_base, 0, "desde")
        assert resultado == fecha_base
    
    def test_direccion_hasta_equivale_desde(self):
        """Dirección 'hasta' se comporta igual que 'desde'."""
        fecha_base = date(2026, 1, 15)
        resultado_hasta = calcular_dias_corridos(fecha_base, 10, "hasta")
        resultado_desde = calcular_dias_corridos(fecha_base, 10, "desde")
        assert resultado_hasta == resultado_desde
    
    def test_direccion_despues_de_equivale_desde(self):
        """Dirección 'después_de' se comporta igual que 'desde'."""
        fecha_base = date(2026, 1, 15)
        resultado_despues = calcular_dias_corridos(fecha_base, 10, "después_de")
        resultado_desde = calcular_dias_corridos(fecha_base, 10, "desde")
        assert resultado_despues == resultado_desde
    
    def test_duracion_negativa_invalida(self):
        """Duración negativa debe lanzar ValidationError."""
        fecha_base = date(2026, 1, 15)
        with pytest.raises(ValidationError, match="duración no puede ser negativa"):
            calcular_dias_corridos(fecha_base, -5, "desde")
    
    def test_direccion_invalida_lanza_error(self):
        """Dirección no válida debe lanzar ValidationError."""
        fecha_base = date(2026, 1, 15)
        with pytest.raises(ValidationError, match="Dirección temporal inválida"):
            calcular_dias_corridos(fecha_base, 10, "invalid_direction")


class TestCalculoDiasHabiles:
    """Pruebas para cálculo de días hábiles (17-2)."""
    
    def test_suma_dias_habiles_solo_semana(self):
        """Suma días hábiles sin atravesar fin de semana."""
        fecha_base = date(2026, 1, 5)  # Lunes
        resultado = calcular_dias_habiles(fecha_base, 3, "desde")
        assert resultado == date(2026, 1, 8)  # Jueves (Lun +3 hábiles)
    
    def test_suma_dias_habiles_salta_fin_semana(self):
        """Días hábiles saltan sábado y domingo."""
        fecha_base = date(2026, 1, 9)  # Viernes
        resultado = calcular_dias_habiles(fecha_base, 1, "desde")
        assert resultado == date(2026, 1, 12)  # Lunes siguiente
    
    def test_suma_dias_habiles_multiple_fines_semana(self):
        """Días hábiles atraviesan múltiples fines de semana."""
        fecha_base = date(2026, 1, 5)  # Lunes
        resultado = calcular_dias_habiles(fecha_base, 10, "desde")
        # 5 días + fin semana + 5 días = 2 semanas
        assert resultado == date(2026, 1, 19)  # Lunes 2 semanas después
    
    def test_inicio_en_sabado_comienza_lunes(self):
        """Si fecha base es sábado, comienza conteo desde lunes."""
        fecha_base = date(2026, 1, 10)  # Sábado
        resultado = calcular_dias_habiles(fecha_base, 1, "desde")
        assert resultado == date(2026, 1, 13)  # Martes (Lun+1)
    
    def test_inicio_en_domingo_comienza_lunes(self):
        """Si fecha base es domingo, comienza conteo desde lunes."""
        fecha_base = date(2026, 1, 11)  # Domingo
        resultado = calcular_dias_habiles(fecha_base, 1, "desde")
        assert resultado == date(2026, 1, 13)  # Martes (Lun+1)
    
    def test_resta_dias_habiles_antes_de(self):
        """Resta días hábiles hacia atrás (antes_de)."""
        fecha_base = date(2026, 1, 15)  # Jueves
        resultado = calcular_dias_habiles(fecha_base, 5, "antes_de")
        assert resultado == date(2026, 1, 8)  # Jueves anterior
    
    def test_resta_dias_habiles_salta_fin_semana_atras(self):
        """Resta días hábiles salta fin de semana hacia atrás."""
        fecha_base = date(2026, 1, 12)  # Lunes
        resultado = calcular_dias_habiles(fecha_base, 1, "antes_de")
        assert resultado == date(2026, 1, 9)  # Viernes anterior
    
    def test_cero_dias_habiles_retorna_misma_fecha_si_habil(self):
        """Cero días retorna la fecha base si es día hábil."""
        fecha_base = date(2026, 1, 15)  # Jueves
        resultado = calcular_dias_habiles(fecha_base, 0, "desde")
        assert resultado == fecha_base
    
    def test_cero_dias_habiles_avanza_si_fin_semana(self):
        """Cero días desde fin de semana avanza a lunes."""
        fecha_base = date(2026, 1, 10)  # Sábado
        resultado = calcular_dias_habiles(fecha_base, 0, "desde")
        assert resultado == date(2026, 1, 12)  # Lunes
    
    def test_duracion_negativa_invalida_habiles(self):
        """Duración negativa debe lanzar ValidationError."""
        fecha_base = date(2026, 1, 15)
        with pytest.raises(ValidationError, match="duración no puede ser negativa"):
            calcular_dias_habiles(fecha_base, -3, "desde")


class TestValidacionPlazos:
    """Pruebas para validación de plazos antes del cálculo (17-4)."""
    
    def test_plazo_valido_sin_errores(self):
        """Plazo bien formado pasa validación."""
        analysis_id = "analysis-123"
        
        # Evento con fecha
        evento = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="event-1",
            name="Apertura",
            event_date=date(2026, 1, 15),
            date_source="user_input"  # No requiere source_document_id
        )
        
        # Plazo que depende del evento
        plazo = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="deadline-1",
            name="Presentación de consultas",
            trigger_event_id="event-1",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        # No debe lanzar error
        validar_plazo_antes_calculo(plazo, {"event-1": evento})
    
    def test_plazo_sin_trigger_event_invalido(self):
        """Plazo sin evento disparador debe fallar."""
        analysis_id = "analysis-123"
        
        plazo = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="deadline-1",
            name="Plazo sin trigger",
            trigger_event_id=None,
            duration=10,
            unit="días",
            day_type="corridos"
        )
        
        with pytest.raises(ValidationError, match="falta evento disparador.*trigger_event_id requerido"):
            validar_plazo_antes_calculo(plazo, {})
    
    def test_plazo_con_trigger_inexistente_invalido(self):
        """Plazo que apunta a evento inexistente debe fallar."""
        analysis_id = "analysis-123"
        
        plazo = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="deadline-1",
            name="Plazo con evento inexistente",
            trigger_event_id="event-999",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        with pytest.raises(ValidationError, match="evento disparador.*event-999.*no existe"):
            validar_plazo_antes_calculo(plazo, {})
    
    def test_plazo_dias_habiles_sin_direccion_invalido(self):
        """Días hábiles requieren dirección explícita."""
        analysis_id = "analysis-123"
        
        evento = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="event-1",
            name="Evento",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        plazo = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="deadline-1",
            name="Plazo hábil sin dirección",
            trigger_event_id="event-1",
            duration=10,
            unit="días",
            day_type="hábiles",
            direccion=None
        )
        
        with pytest.raises(ValidationError, match="dirección temporal requerida"):
            validar_plazo_antes_calculo(plazo, {"event-1": evento})


class TestMotorRecalculoCascada:
    """Pruebas para motor de recálculo en cascada (17-3)."""
    
    def test_cascada_lineal_simple(self):
        """Cascada lineal: E1 -> D1 -> E2 -> D2 -> E3."""
        analysis_id = "analysis-123"
        
        # E1 tiene fecha conocida
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Apertura",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        # E2 y E3 sin fecha
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Consultas",
            event_date=None,
            date_source="pending"
        )
        
        e3 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e3",
            name="Presentación",
            event_date=None,
            date_source="pending"
        )
        
        # D1: 10 días corridos desde E1 -> E2
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="Plazo consultas",
            trigger_event_id="e1",
            target_event_id="e2",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        # D2: 5 días hábiles desde E2 -> E3
        d2 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d2",
            name="Plazo presentación",
            trigger_event_id="e2",
            target_event_id="e3",
            duration=5,
            unit="días",
            day_type="hábiles",
            direccion="desde"
        )
        
        eventos, deadlines = calcular_fechas_cascada(
            [e1, e2, e3],
            [d1, d2]
        )
        
        # Verificar fechas calculadas
        eventos_dict = {e.event_id: e for e in eventos}
        deadlines_dict = {d.deadline_id: d for d in deadlines}
        
        # E1 mantiene su fecha
        assert eventos_dict["e1"].event_date == date(2026, 1, 15)
        
        # E2 = E1 + 10 días corridos = 2026-01-25
        assert eventos_dict["e2"].event_date == date(2026, 1, 25)
        assert eventos_dict["e2"].date_source == "calculated"
        
        # D1 debe tener fecha calculada
        assert deadlines_dict["d1"].deadline_date == date(2026, 1, 25)
        assert deadlines_dict["d1"].calculation_status == "calculated"
        
        # E3 = E2 + 5 días hábiles
        # E2 es domingo 25 -> siguiente lunes 27 -> +5 hábiles
        # Lunes 27 + (Mar 28, Mié 29, Jue 30, Vie 31, Lun 2) = 2 feb (lunes)
        assert eventos_dict["e3"].event_date == date(2026, 2, 2)
        assert eventos_dict["e3"].date_source == "calculated"
    
    def test_cascada_multiples_dependencias_mismo_evento(self):
        """Múltiples plazos que producen el mismo evento target."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Evento A",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Evento B",
            event_date=date(2026, 1, 20),
            date_source="user_input"
        )
        
        e3 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e3",
            name="Evento Target",
            event_date=None,
            date_source="pending"
        )
        
        # Dos plazos apuntan al mismo target E3
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="Desde A",
            trigger_event_id="e1",
            target_event_id="e3",
            duration=15,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        d2 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d2",
            name="Desde B",
            trigger_event_id="e2",
            target_event_id="e3",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        eventos, deadlines = calcular_fechas_cascada([e1, e2, e3], [d1, d2])
        eventos_dict = {e.event_id: e for e in eventos}
        
        # E3 debe tomar la fecha MÁS TEMPRANA de ambas opciones
        # D1: 2026-01-15 + 15 = 2026-01-30
        # D2: 2026-01-20 + 10 = 2026-01-30
        # Ambas dan la misma fecha en este caso
        assert eventos_dict["e3"].event_date == date(2026, 1, 30)
    
    def test_cascada_multiples_dependencias_diferentes_fechas(self):
        """Múltiples plazos con fechas DIFERENTES - verifica lógica min()."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Evento A",
            event_date=date(2026, 1, 10),
            date_source="user_input"
        )
        
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Evento B",
            event_date=date(2026, 1, 20),
            date_source="user_input"
        )
        
        e3 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e3",
            name="Evento Target",
            event_date=None,
            date_source="pending"
        )
        
        # D1: E1 + 15 días = 2026-01-25
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="Desde A",
            trigger_event_id="e1",
            target_event_id="e3",
            duration=15,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        # D2: E2 + 5 días = 2026-01-25 (¡misma fecha!)
        # Cambiamos para tener fechas DIFERENTES
        d2 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d2",
            name="Desde B",
            trigger_event_id="e2",
            target_event_id="e3",
            duration=15,  # E2 (20 ene) + 15 = 4 feb
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        eventos, deadlines = calcular_fechas_cascada([e1, e2, e3], [d1, d2])
        eventos_dict = {e.event_id: e for e in eventos}
        
        # E3 debe tomar la fecha MÁS TEMPRANA:
        # D1: 2026-01-10 + 15 = 2026-01-25
        # D2: 2026-01-20 + 15 = 2026-02-04
        # min(25 ene, 4 feb) = 25 ene
        assert eventos_dict["e3"].event_date == date(2026, 1, 25)
        assert eventos_dict["e3"].date_source == "calculated"
    
    def test_cascada_respeta_fechas_existentes_no_sobrescribe(self):
        """Eventos con fecha existente NO deben ser sobrescritos por cascada."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Trigger",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        # E2 YA tiene fecha (user_input) - no debe cambiar
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Target con fecha fija",
            event_date=date(2026, 2, 1),  # Fecha existente
            date_source="user_input"
        )
        
        # D1 intentaría calcular E2 como 15 ene + 10 = 25 ene
        # Pero E2 ya tiene fecha, así que no debe cambiar
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="Plazo",
            trigger_event_id="e1",
            target_event_id="e2",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        eventos, deadlines = calcular_fechas_cascada([e1, e2], [d1])
        eventos_dict = {e.event_id: e for e in eventos}
        
        # E2 debe mantener su fecha original (2026-02-01)
        assert eventos_dict["e2"].event_date == date(2026, 2, 1)
        assert eventos_dict["e2"].date_source == "user_input"
        
        # D1 se calcula correctamente pero no modifica E2
        deadlines_dict = {d.deadline_id: d for d in deadlines}
        assert deadlines_dict["d1"].deadline_date == date(2026, 1, 25)
        assert deadlines_dict["d1"].calculation_status == "calculated"
    
    def test_cascada_dependencia_circular_detectada(self):
        """Detecta dependencias circulares: E1 -> D1 -> E2 -> D2 -> E1."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Evento 1",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Evento 2",
            event_date=None,
            date_source="pending"
        )
        
        # D1: E1 -> E2
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="1 a 2",
            trigger_event_id="e1",
            target_event_id="e2",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        # D2: E2 -> E1 (circular!)
        d2 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d2",
            name="2 a 1",
            trigger_event_id="e2",
            target_event_id="e1",
            duration=5,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        with pytest.raises(CircularDependencyError, match="Dependencia circular"):
            calcular_fechas_cascada([e1, e2], [d1, d2])
    
    def test_cascada_evento_sin_fecha_trigger_genera_error(self):
        """Plazo con trigger sin fecha queda en estado pending."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Sin fecha",
            event_date=None,
            date_source="pending"
        )
        
        e2 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e2",
            name="Target",
            event_date=None,
            date_source="pending"
        )
        
        d1 = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            deadline_id="d1",
            name="Plazo pendiente",
            trigger_event_id="e1",
            target_event_id="e2",
            duration=10,
            unit="días",
            day_type="corridos",
            direccion="desde"
        )
        
        eventos, deadlines = calcular_fechas_cascada([e1, e2], [d1])
        deadlines_dict = {d.deadline_id: d for d in deadlines}
        
        # D1 debe quedar en status pending (no error, solo sin calcular)
        assert deadlines_dict["d1"].calculation_status == "pending"
        assert "evento disparador sin fecha" in deadlines_dict["d1"].calculation_error.lower()
    
    def test_cascada_sin_deadlines_no_cambia_eventos(self):
        """Sin deadlines, eventos mantienen su estado."""
        analysis_id = "analysis-123"
        
        e1 = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            event_id="e1",
            name="Evento",
            event_date=date(2026, 1, 15),
            date_source="user_input"
        )
        
        eventos, deadlines = calcular_fechas_cascada([e1], [])
        
        assert len(eventos) == 1
        assert eventos[0].event_date == date(2026, 1, 15)
        assert len(deadlines) == 0
