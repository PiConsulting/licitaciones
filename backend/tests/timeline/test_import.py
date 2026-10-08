"""Test simple de import del módulo timeline."""


def test_import_timeline_models():
    """El módulo timeline.models debe poderse importar."""
    from timeline.models import Event, DateSource, EventStatus
    assert Event is not None
    assert DateSource is not None
    assert EventStatus is not None


def test_create_simple_event():
    """Se debe poder crear un Event básico."""
    from timeline.models import Event
    
    event = Event(
        partition_key="test-123",
        analysis_id="test-123",
        name="Test Event"
    )
    
    assert event.name == "Test Event"
    assert event.partition_key == "test-123"
    assert event.type == "event"
    assert event.deleted is False
