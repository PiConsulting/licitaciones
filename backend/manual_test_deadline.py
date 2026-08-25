"""Verificación manual del modelo Deadline."""
from datetime import date

from timeline.models import Deadline


def test_basic_deadline():
    """Test básico de creación de deadline sin fecha."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Presentación de Ofertas"
    )
    
    assert deadline.name == "Presentación de Ofertas"
    assert deadline.partition_key == "test-123"
    assert deadline.type == "deadline"
    assert deadline.deleted is False
    assert deadline.deadline_date is None
    assert deadline.date_source == "pending"
    assert deadline.status == "pending"
    print("[PASS] test_basic_deadline")


def test_deadline_with_detected_date():
    """Test de deadline con fecha detectada."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Cierre de Ofertas",
        deadline_date=date(2026, 9, 20),
        date_source="detected",
        source_document_id="doc-456",
        source_page=3,
    )
    
    assert deadline.deadline_date == date(2026, 9, 20)
    assert deadline.date_source == "detected"
    assert deadline.source_document_id == "doc-456"
    print("[PASS] test_deadline_with_detected_date")


def test_deadline_calculated_requires_period_info():
    """Test que calculated requiere period_value, period_type y reference_event_id."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Adjudicación",
            deadline_date=date(2026, 10, 1),  # Con fecha para pasar primera validación
            date_source="calculated",
            # Faltan period_value, period_type, reference_event_id
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "date_source='calculated' requiere" in str(e)
        print("[PASS] test_deadline_calculated_requires_period_info")


def test_deadline_with_calculated_date():
    """Test de deadline calculado con plazo relativo."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Presentación Ofertas",
        deadline_date=date(2026, 9, 25),
        date_source="calculated",
        period_value=5,
        period_type="business_days",
        reference_event_id="event::abc-123",
    )
    
    assert deadline.deadline_date == date(2026, 9, 25)
    assert deadline.date_source == "calculated"
    assert deadline.period_value == 5
    assert deadline.period_type == "business_days"
    assert deadline.reference_event_id == "event::abc-123"
    print("[PASS] test_deadline_with_calculated_date")


def test_deadline_validation_null_date_requires_pending():
    """Test que deadline_date=None requiere date_source='pending'."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Test",
            deadline_date=None,
            date_source="detected",  # Debe fallar
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "Si deadline_date es null, date_source debe ser 'pending'" in str(e)
        print("[PASS] test_deadline_validation_null_date_requires_pending")


def test_deadline_validation_detected_requires_source():
    """Test que detected requiere source_document_id."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Test",
            deadline_date=date(2026, 1, 1),
            date_source="detected",
            source_document_id=None,  # Debe fallar
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "date_source='detected' requiere source_document_id" in str(e)
        print("[PASS] test_deadline_validation_detected_requires_source")


def test_deadline_auto_generates_ids():
    """Test que IDs se generan automáticamente."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Test"
    )
    
    assert deadline.id.startswith("deadline::")
    assert len(deadline.deadline_id) == 36  # UUID format
    print("[PASS] test_deadline_auto_generates_ids")


if __name__ == "__main__":
    print("=== Manual Deadline Model Tests ===\n")
    test_basic_deadline()
    test_deadline_with_detected_date()
    test_deadline_calculated_requires_period_info()
    test_deadline_with_calculated_date()
    test_deadline_validation_null_date_requires_pending()
    test_deadline_validation_detected_requires_source()
    test_deadline_auto_generates_ids()
    print("\n🎉 ¡Todos los tests de Deadline pasaron!")
