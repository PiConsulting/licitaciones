"""
Tests para el motor de recálculo de fechas en cascada.
"""
from datetime import date
from unittest.mock import Mock

import pytest

from timeline.calculation_engine import recalculate_dependent_dates
from timeline.models import Deadline, Event


class TestCalculationEngine:
    """Tests para el motor de cálculo en cascada."""

    def test_recalculate_simple_dependency(self):
        """AC1: Recalcular dependencia simple A→B (síncrono para simplicidad)"""
        mock_service = Mock()

        event_adj = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="adj-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input"
        )
        
        event_entrega = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="entrega-1",
            name="Entrega",
            event_date=None,
            date_source="pending"
        )
        
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo entrega",
            trigger_event_id="adj-1",
            target_event_id="entrega-1",
            duration=45,
            day_type="corridos",
            calculation_status="pending"
        )
        
        mock_service.get_event.return_value = event_adj
        mock_service.list_deadlines.return_value = [deadline]

        result = recalculate_dependent_dates(mock_service, "analysis-1", "adj-1")

        assert result.events_updated == 1
        assert len(result.errors) == 0

        mock_service.update_deadline.assert_called_once()
        updated_deadline = mock_service.update_deadline.call_args[0][0]
        assert updated_deadline.deadline_date == date(2026, 10, 25)
        assert updated_deadline.calculation_status == "calculated"

        mock_service.update_event.assert_called_once()
        updated_event = mock_service.update_event.call_args[0][0]
        assert updated_event.event_date == date(2026, 10, 25)
        assert updated_event.date_source == "calculated"

    def test_recalculate_with_day_type_no_especificado(self):
        """AC2: day_type='no_especificado' debe marcar error"""
        mock_service = Mock()
        
        event_adj = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="adj-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input"
        )
        
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo sin tipo",
            trigger_event_id="adj-1",
            target_event_id="entrega-1",
            duration=45,
            day_type="no_especificado",
            calculation_status="pending"
        )

        mock_service.get_event.return_value = event_adj
        mock_service.list_deadlines.return_value = [deadline]

        result = recalculate_dependent_dates(mock_service, "analysis-1", "adj-1")

        assert result.events_updated == 0
        assert len(result.errors) == 1
        assert "tipo de día no especificado" in result.errors[0].lower()

        updated_deadline = mock_service.update_deadline.call_args[0][0]
        assert updated_deadline.calculation_status == "error"
        assert "no especificado" in updated_deadline.calculation_error.lower()

    def test_recalculate_trigger_event_without_date(self):
        """AC3: Evento trigger sin fecha debe mantener pending"""
        mock_service = Mock()
        
        event_pending = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="pending-1",
            name="Evento Pendiente",
            event_date=None,
            date_source="pending"
        )
        
        mock_service.get_event.return_value = event_pending
        # se llama list_deadlines incluso sin fecha en el trigger
        mock_service.list_deadlines.return_value = []

        result = recalculate_dependent_dates(mock_service, "analysis-1", "pending-1")

        assert result.events_updated == 0
        assert len(result.errors) == 1
        assert "no tiene fecha asignada" in result.errors[0]

    def test_recalculate_detects_cycle(self):
        """AC4: Debe detectar ciclo A→B→C→A"""
        mock_service = Mock()
        
        event_a = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="a",
            name="A",
            event_date=date(2026, 9, 1),
            date_source="user_input"
        )
        
        result = recalculate_dependent_dates(
            mock_service,
            "analysis-1",
            "a",
            visited={"a"}  # Simula que ya visitamos 'a'
        )

        assert result.events_updated == 0
        assert len(result.errors) > 0
        assert "ciclo" in result.errors[0].lower()

    def test_recalculate_cascades_to_dependent(self):
        """Recálculo debe propagarse en cascada A→B→C"""
        mock_service = Mock()

        # A → B (10 días) → C (5 días)
        event_a = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="a",
            name="A",
            event_date=date(2026, 9, 1),
            date_source="user_input"
        )
        
        event_b = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="b",
            name="B"
        )
        
        event_c = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="c",
            name="C"
        )
        
        deadline_ab = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-ab",
            name="A→B",
            trigger_event_id="a",
            target_event_id="b",
            duration=10,
            day_type="corridos"
        )
        
        deadline_bc = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-bc",
            name="B→C",
            trigger_event_id="b",
            target_event_id="c",
            duration=5,
            day_type="corridos"
        )
        
        # Mock responses: simular recursión
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "a":
                return event_a
            elif event_id == "b":
                # B se actualiza durante recursión
                event_b.event_date = date(2026, 9, 11)
                event_b.date_source = "calculated"
                return event_b
            elif event_id == "c":
                return event_c
        
        def list_deadlines_side_effect(analysis_id, user_id=None):
            return [deadline_ab, deadline_bc]

        mock_service.get_event.side_effect = get_event_side_effect
        mock_service.list_deadlines.return_value = [deadline_ab]

        result = recalculate_dependent_dates(mock_service, "analysis-1", "a")

        assert result.events_updated >= 1
        assert len(result.errors) == 0
