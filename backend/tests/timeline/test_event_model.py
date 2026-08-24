"""Tests para el modelo Event de Timeline."""
from datetime import date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from timeline.models import Event


class TestEventModel:
    """Tests para el modelo Event."""

    def test_event_pending_without_date(self):
        """Evento sin fecha debe tener date_source='pending'."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Adjudicación",
            event_date=None,
            date_source="pending",
        )
        
        assert event.event_date is None
        assert event.event_date_source == "pending"
        assert event.status == "pending"
        assert event.deleted is False

    def test_event_detected_requires_source(self):
        """date_source='detected' requiere source_document_id."""
        with pytest.raises(ValidationError) as exc_info:
            Event(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Apertura",
                event_date=date(2026, 9, 15),
                date_source="detected",
                source_document_id=None,  # Debe fallar
            )
        
        assert "date_source='detected' requiere source_document_id" in str(exc_info.value)

    def test_event_with_null_date_requires_pending_source(self):
        """Si date es null, date_source debe ser 'pending'."""
        with pytest.raises(ValidationError) as exc_info:
            Event(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Firma de Contrato",
                event_date=None,
                date_source="detected",  # Debe fallar
            )
        
        assert "Si date es null, date_source debe ser 'pending'" in str(exc_info.value)

    def test_event_with_detected_source_and_document_id(self):
        """Evento con fecha detectada debe incluir source_document_id."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Apertura de Ofertas",
            event_date=date(2026, 9, 10),
            date_source="detected",
            source_document_id="doc-456",
            source_page=5,
            source_fragment="La apertura de ofertas tendrá lugar el 10 de septiembre de 2026.",
        )
        
        assert event.event_date == date(2026, 9, 10)
        assert event.event_date_source == "detected"
        assert event.source_document_id == "doc-456"
        assert event.source_page == 5
        assert event.source_fragment is not None

    def test_event_with_user_input_source(self):
        """Evento con fecha ingresada por usuario."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Entrega Final",
            event_date=date(2026, 12, 15),
            date_source="user_input",
            status="confirmed",
        )
        
        assert event.event_date == date(2026, 12, 15)
        assert event.event_date_source == "user_input"
        assert event.status == "confirmed"

    def test_event_with_calculated_source(self):
        """Evento con fecha calculada por el motor."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Vencimiento Consultas",
            event_date=date(2026, 9, 20),
            date_source="calculated",
        )
        
        assert event.event_date == date(2026, 9, 20)
        assert event.event_date_source == "calculated"

    def test_event_auto_generates_ids(self):
        """Event debe auto-generar IDs si no se proveen."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Adjudicación",
        )
        
        # Verificar que id tiene formato event::<uuid>
        assert event.id.startswith("event::")
        uuid_part = event.id.replace("event::", "")
        assert UUID(uuid_part)  # Valida que es un UUID válido
        
        # Verificar que event_id es un UUID válido
        assert UUID(event.event_id)

    def test_event_type_is_fixed(self):
        """El campo type debe ser siempre 'event'."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Apertura",
        )
        
        assert event.type == "event"

    def test_event_partition_key_matches_analysis_id(self):
        """partition_key debe usarse para particionar por analysis_id."""
        analysis_id = "analysis-abc-123"
        event = Event(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            name="Adjudicación",
        )
        
        assert event.partition_key == analysis_id
        assert event.analysis_id == analysis_id

    def test_event_timestamps_auto_generated(self):
        """created_at y updated_at deben auto-generarse."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Apertura",
        )
        
        assert isinstance(event.created_at, datetime)
        assert isinstance(event.updated_at, datetime)

    def test_event_with_source_reference(self):
        """Evento puede incluir source_reference dict."""
        source_ref = {
            "confidence": 0.95,
            "extraction_method": "azure_di",
        }
        
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Adjudicación",
            event_date=date(2026, 10, 1),
            date_source="detected",
            source_document_id="doc-789",
            source_reference=source_ref,
        )
        
        assert event.source_reference == source_ref

    def test_event_invalid_date_source_value(self):
        """date_source debe ser uno de los valores permitidos."""
        with pytest.raises(ValidationError):
            Event(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Apertura",
                date_source="invalid_source",  # Valor inválido
            )

    def test_event_invalid_status_value(self):
        """status debe ser 'pending' o 'confirmed'."""
        with pytest.raises(ValidationError):
            Event(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Apertura",
                status="invalid_status",  # Valor inválido
            )

    def test_event_soft_delete_flag(self):
        """Campo deleted debe existir para soft delete."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Adjudicación",
            deleted=True,
        )
        
        assert event.deleted is True

    def test_event_name_required(self):
        """name es un campo requerido."""
        with pytest.raises(ValidationError):
            Event(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                # name falta
            )

    def test_event_analysis_id_required(self):
        """analysis_id es un campo requerido."""
        with pytest.raises(ValidationError):
            Event(
                partition_key="analysis-123",
                # analysis_id falta
                name="Adjudicación",
            )

    def test_event_partition_key_required(self):
        """partition_key es un campo requerido."""
        with pytest.raises(ValidationError):
            Event(
                # partition_key falta
                analysis_id="analysis-123",
                name="Adjudicación",
            )

    def test_event_serialization_to_dict(self):
        """Event debe poder serializarse a dict para Cosmos."""
        event = Event(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Apertura de Ofertas",
            event_date=date(2026, 9, 15),
            date_source="detected",
            source_document_id="doc-456",
            source_page=3,
            source_fragment="La apertura será el 15/09/2026",
        )
        
        event_dict = event.model_dump()
        
        assert event_dict["type"] == "event"
        assert event_dict["name"] == "Apertura de Ofertas"
        assert event_dict["partition_key"] == "analysis-123"
        assert event_dict["date_source"] == "detected"
        assert event_dict["deleted"] is False
