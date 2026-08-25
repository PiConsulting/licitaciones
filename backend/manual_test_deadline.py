"""Verificación manual del modelo Deadline."""
from datetime import date

from timeline.models import Deadline


def test_basic_deadline():
    """Test básico de creación de deadline sin fecha calculada."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Presentación de Ofertas",
        duration=10  # Campo requerido
    )
    
    assert deadline.name == "Presentación de Ofertas"
    assert deadline.partition_key == "test-123"
    assert deadline.type == "deadline"
    assert deadline.deleted is False
    assert deadline.deadline_date is None
    assert deadline.calculation_status == "pending"
    assert deadline.duration == 10
    assert deadline.unit == "días"
    print("✓ test_basic_deadline passed")


def test_deadline_with_calculated_date():
    """Test de deadline con fecha ya calculada."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Cierre de Ofertas",
        duration=15,
        unit="días",
        day_type="hábiles",
        trigger_event_id="event-abc",
        target_event_id="event-xyz",
        deadline_date=date(2026, 9, 20),
        calculation_status="calculated",
        source_document_id="doc-456",
        source_page=3,
    )
    
    assert deadline.deadline_date == date(2026, 9, 20)
    assert deadline.calculation_status == "calculated"
    assert deadline.source_document_id == "doc-456"
    assert deadline.duration == 15
    assert deadline.unit == "días"
    assert deadline.day_type == "hábiles"
    print("✓ test_deadline_with_calculated_date passed")


def test_deadline_validation_calculated_requires_date():
    """Test que calculated requiere deadline_date."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Adjudicación",
            duration=5,
            calculation_status="calculated",
            # Falta deadline_date
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "calculated" in str(e).lower()
        print("✓ test_deadline_validation_calculated_requires_date passed")


def test_deadline_validation_pending_with_date():
    """Test que pending no puede tener deadline_date."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Presentación Ofertas",
            duration=10,
            deadline_date=date(2026, 9, 25),
            calculation_status="pending",
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "pending" in str(e).lower()
        print("✓ test_deadline_validation_pending_with_date passed")


def test_deadline_validation_error_requires_message():
    """Test que error requiere calculation_error."""
    try:
        Deadline(
            partition_key="test-123",
            analysis_id="test-123",
            name="Test",
            duration=5,
            calculation_status="error",
            # Falta calculation_error
        )
        assert False, "Debería haber lanzado ValidationError"
    except ValueError as e:
        assert "error" in str(e).lower()
        print("✓ test_deadline_validation_error_requires_message passed")


def test_deadline_with_error_status():
    """Test deadline con error de cálculo."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Test Error",
        duration=10,
        calculation_status="error",
        calculation_error="Evento disparador sin fecha"
    )
    
    assert deadline.calculation_status == "error"
    assert deadline.calculation_error == "Evento disparador sin fecha"
    assert deadline.deadline_date is None
    print("✓ test_deadline_with_error_status passed")


def test_deadline_auto_generates_ids():
    """Test que se generan IDs automáticamente."""
    deadline = Deadline(
        partition_key="test-123",
        analysis_id="test-123",
        name="Test IDs",
        duration=5
    )
    
    assert deadline.id.startswith("deadline::")
    assert deadline.deadline_id  # UUID generado
    assert deadline.created_at is not None
    assert deadline.updated_at is not None
    print("✓ test_deadline_auto_generates_ids passed")


if __name__ == "__main__":
    print("=== Manual Deadline Model Tests ===\n")
    test_basic_deadline()
    test_deadline_with_calculated_date()
    test_deadline_validation_calculated_requires_date()
    test_deadline_validation_pending_with_date()
    test_deadline_validation_error_requires_message()
    test_deadline_with_error_status()
    test_deadline_auto_generates_ids()
    print("\n🎉 ¡Todos los tests manuales de Deadline pasaron!")
