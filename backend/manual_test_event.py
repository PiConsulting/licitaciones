"""Verificación manual del modelo Event."""
from datetime import date

from timeline.models import Event


def test_basic_event():
    """Test básico de creación de evento."""
    event = Event(
        partition_key="test-123",
        analysis_id="test-123",
        name="Apertura de Ofertas"
    )
    
    assert event.name == "Apertura de Ofertas"
    assert event.partition_key == "test-123"
    assert event.type == "event"
    assert event.deleted is False
    assert event.event_date is None
    assert event.date_source == "pending"
    print("✓ test_basic_event passed")


def test_event_with_detected_date():
    """Test de evento con fecha detectada."""
    event = Event(
        partition_key="test-123",
        analysis_id="test-123",
        name="Apertura",
        event_date=date(2026, 9, 15),
        date_source="detected",
        source_document_id="doc-456",
        source_page=5,
    )
    
    assert event.event_date == date(2026, 9, 15)
    assert event.date_source == "detected"
    assert event.source_document_id == "doc-456"
    print("✓ test_event_with_detected_date passed")


def test_event_validation_null_date_requires_pending():
    """Test que event_date=None requiere date_source='pending'."""
    try:
        Event(
            partition_key="test-123",
            analysis_id="test-123",
            name="Test",
            event_date=None,
            date_source="detected",  # Debe fallar
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "Si event_date es null, date_source debe ser 'pending'" in str(e)
        print("✓ test_event_validation_null_date_requires_pending passed")


def test_event_validation_detected_requires_source():
    """Test que detected requiere source_document_id."""
    try:
        Event(
            partition_key="test-123",
            analysis_id="test-123",
            name="Test",
            event_date=date(2026, 1, 1),
            date_source="detected",
            source_document_id=None,  # Debe fallar
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "date_source='detected' requiere source_document_id" in str(e)
        print("✓ test_event_validation_detected_requires_source passed")


def test_event_auto_generates_ids():
    """Test que IDs se generan automáticamente."""
    event = Event(
        partition_key="test-123",
        analysis_id="test-123",
        name="Test"
    )
    
    assert event.id.startswith("event::")
    assert len(event.event_id) == 36  # UUID format
    print("✓ test_event_auto_generates_ids passed")


if __name__ == "__main__":
    test_basic_event()
    test_event_with_detected_date()
    test_event_validation_null_date_requires_pending()
    test_event_validation_detected_requires_source()
    test_event_auto_generates_ids()
    print("\n🎉 ¡Todos los tests manuales pasaron!")
