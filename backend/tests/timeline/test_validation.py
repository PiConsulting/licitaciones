"""
Tests para validaciones de Timeline.
"""
from datetime import date
from unittest.mock import Mock

import pytest

from timeline.models import Deadline, Event
from timeline.validation import ValidationResult, validate_deadline_for_calculation


class TestDeadlineValidation:
    """Tests para validación de deadlines antes de cálculo."""

    def test_validate_deadline_all_valid(self):
        """AC1: Deadline válido pasa validación"""
        mock_service = Mock()
        
        # Trigger con fecha
        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input"
        )
        
        # Target event
        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega"
        )
        
        # Deadline válido
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo entrega",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=45,
            unit="días",
            day_type="corridos"
        )
        
        # Mock responses
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target
        
        mock_service.get_event.side_effect = get_event_side_effect
        
        # Execute
        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)
        
        # Assert (AC2)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_deadline_trigger_without_date(self):
        """AC1 y AC3: Falla si evento trigger no tiene fecha"""
        mock_service = Mock()
        
        # Trigger SIN fecha
        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=None,  # Sin fecha
            date_source="pending"
        )
        
        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega"
        )
        
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=45,
            day_type="corridos"
        )
        
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target
        
        mock_service.get_event.side_effect = get_event_side_effect
        
        # Execute
        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)
        
        # Assert
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("no tiene fecha" in e.lower() for e in result.errors)

    def test_validate_deadline_day_type_no_especificado(self):
        """AC1 y AC3: Falla si day_type es 'no_especificado'"""
        mock_service = Mock()
        
        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input"
        )
        
        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega"
        )
        
        # day_type no especificado
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=45,
            day_type="no_especificado"  # Inválido
        )
        
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target
        
        mock_service.get_event.side_effect = get_event_side_effect
        
        # Execute
        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)
        
        # Assert
        assert result.is_valid is False
        assert any("no especificado" in e.lower() for e in result.errors)

    def test_validate_deadline_invalid_unit(self):
        """AC1: Falla si unidad no es 'días'"""
        mock_service = Mock()
        
        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input"
        )
        
        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega"
        )
        
        # Unidad no soportada
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=2,
            unit="meses",  # No soportado aún
            day_type="corridos"
        )
        
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target
        
        mock_service.get_event.side_effect = get_event_side_effect
        
        # Execute
        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)
        
        # Assert
        assert result.is_valid is False
        assert any("no soportada" in e.lower() for e in result.errors)

    def test_validate_deadline_direccion_hasta_not_calculable_yet(self):
        """2026-09-01: 'hasta'/'antes_de' implicarían calcular hacia atrás,
        que `add_business_days` no soporta -- el Deadline SÍ se materializa
        (ver `timeline/materializer.py::_VALID_DIRECTIONS`), pero acá se
        frena el cálculo con un error claro en vez de sumar días hacia
        adelante como si fuera 'desde' (lo que daría una fecha incorrecta)."""
        mock_service = Mock()

        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Apertura de ofertas",
            event_date=date(2026, 9, 10),
            date_source="user_input",
        )

        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Presentación de consultas",
        )

        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=5,
            unit="días",
            day_type="hábiles",
            direccion="antes_de",
        )

        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target

        mock_service.get_event.side_effect = get_event_side_effect

        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)

        assert result.is_valid is False
        assert any("hacia atrás" in e.lower() for e in result.errors)

    def test_validate_deadline_direccion_desde_is_fine(self):
        """Control: 'desde' (la dirección que el motor sí sabe calcular) no
        debe agregar ningún error nuevo por la validación de dirección."""
        mock_service = Mock()

        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=date(2026, 9, 10),
            date_source="user_input",
        )

        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega",
        )

        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=45,
            unit="días",
            day_type="corridos",
            direccion="desde",
        )

        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target

        mock_service.get_event.side_effect = get_event_side_effect

        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)

        assert result.is_valid is True
        assert result.errors == []

    def test_validate_deadline_multiple_errors(self):
        """AC3: Debe recolectar múltiples errores"""
        mock_service = Mock()
        
        # Trigger sin fecha
        trigger = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="trigger-1",
            name="Adjudicación",
            event_date=None,  # Error 1
            date_source="pending"
        )
        
        target = Event(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            event_id="target-1",
            name="Entrega"
        )
        
        # Multiple problemas: sin fecha + day_type no especificado
        deadline = Deadline(
            analysis_id="analysis-1",
            partition_key="analysis-1",
            deadline_id="dl-1",
            name="Plazo",
            trigger_event_id="trigger-1",
            target_event_id="target-1",
            duration=45,
            day_type="no_especificado"  # Error 2
        )
        
        def get_event_side_effect(event_id, analysis_id, user_id=None):
            if event_id == "trigger-1":
                return trigger
            elif event_id == "target-1":
                return target
        
        mock_service.get_event.side_effect = get_event_side_effect
        
        # Execute
        result = validate_deadline_for_calculation(mock_service, "analysis-1", deadline)
        
        # Assert - debe detectar AMBOS errores
        assert result.is_valid is False
        assert len(result.errors) >= 2
