"""Tests para el modelo Deadline de Timeline."""
from datetime import date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from timeline.models import Deadline


class TestDeadlineModel:
    """Tests para el modelo Deadline."""

    def test_deadline_pending_sin_fecha(self):
        """Deadline recién extraído: sin fecha, calculation_status='pending'."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de consultas",
            trigger_event_id="evt-1",
            duration=10,
            unit="días",
            day_type="hábiles",
            direccion="antes_de",
        )

        assert deadline.deadline_date is None
        assert deadline.calculation_status == "pending"
        assert deadline.target_event_id is None
        assert deadline.deleted is False

    def test_deadline_calculado_requiere_fecha(self):
        """calculation_status='calculated' sin deadline_date debe fallar."""
        with pytest.raises(ValidationError) as exc_info:
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Presentación de ofertas",
                duration=45,
                unit="días",
                calculation_status="calculated",
                deadline_date=None,
            )

        assert "No puede estar 'calculated' sin deadline_date" in str(exc_info.value)

    def test_deadline_con_fecha_no_puede_quedar_pending(self):
        """Si hay deadline_date, calculation_status no puede ser 'pending'."""
        with pytest.raises(ValidationError) as exc_info:
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Presentación de ofertas",
                duration=45,
                unit="días",
                deadline_date=date(2026, 10, 1),
                calculation_status="pending",
            )

        assert (
            "Si hay deadline_date, calculation_status no puede quedar en 'pending'"
            in str(exc_info.value)
        )

    def test_deadline_calculado_con_fecha_es_valido(self):
        """calculation_status='calculated' con deadline_date es válido."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de ofertas",
            duration=45,
            unit="días",
            deadline_date=date(2026, 10, 1),
            calculation_status="calculated",
        )

        assert deadline.deadline_date == date(2026, 10, 1)
        assert deadline.calculation_status == "calculated"

    def test_deadline_error_requiere_mensaje(self):
        """calculation_status='error' sin calculation_error debe fallar."""
        with pytest.raises(ValidationError) as exc_info:
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Presentación de ofertas",
                duration=45,
                unit="días",
                calculation_status="error",
                calculation_error=None,
            )

        assert "calculation_status='error' requiere calculation_error" in str(
            exc_info.value
        )

    def test_deadline_error_con_mensaje_es_valido(self):
        """calculation_status='error' con calculation_error es válido."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de ofertas",
            duration=45,
            unit="días",
            calculation_status="error",
            calculation_error="Dependencia circular con evento disparador",
        )

        assert deadline.calculation_status == "error"
        assert deadline.calculation_error == "Dependencia circular con evento disparador"

    def test_deadline_duration_puede_ser_cero(self):
        """duration=0 es válido (ej. 'a continuación de la emisión de la orden')."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Inicio de obra",
            duration=0,
            unit="días",
        )

        assert deadline.duration == 0

    def test_deadline_duration_negativa_invalida(self):
        """duration negativa debe fallar (ge=0)."""
        with pytest.raises(ValidationError):
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Inicio de obra",
                duration=-1,
                unit="días",
            )

    def test_deadline_day_type_default_no_especificado(self):
        """day_type por defecto debe ser 'no_especificado' (anti-invención)."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de ofertas",
            duration=45,
        )

        assert deadline.day_type == "no_especificado"

    def test_deadline_unit_default_dias(self):
        """unit por defecto debe ser 'días'."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de ofertas",
            duration=45,
        )

        assert deadline.unit == "días"

    def test_deadline_es_plazo_maximo_default_false(self):
        """es_plazo_maximo por defecto debe ser False."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Ejecución de obra",
            duration=90,
        )

        assert deadline.es_plazo_maximo is False

    def test_deadline_trigger_y_target_event_ids(self):
        """trigger_event_id y target_event_id vinculan eventos."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de consultas",
            trigger_event_id="evt-apertura",
            target_event_id="evt-vencimiento-consultas",
            duration=10,
            unit="días",
            day_type="hábiles",
            direccion="antes_de",
        )

        assert deadline.trigger_event_id == "evt-apertura"
        assert deadline.target_event_id == "evt-vencimiento-consultas"

    def test_deadline_direccion_valores_validos(self):
        """direccion acepta desde|hasta|antes_de|después_de."""
        for valor in ("desde", "hasta", "antes_de", "después_de"):
            deadline = Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Plazo",
                duration=5,
                direccion=valor,
            )
            assert deadline.direccion == valor

    def test_deadline_unit_invalida(self):
        """unit debe ser uno de los valores permitidos."""
        with pytest.raises(ValidationError):
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Plazo",
                duration=5,
                unit="semanas",  # inválido
            )

    def test_deadline_auto_genera_ids(self):
        """Deadline debe auto-generar id y deadline_id."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Plazo",
            duration=5,
        )

        assert deadline.id.startswith("deadline::")
        uuid_part = deadline.id.replace("deadline::", "")
        assert UUID(uuid_part)
        assert UUID(deadline.deadline_id)

    def test_deadline_type_es_fijo(self):
        """El campo type debe ser siempre 'deadline'."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Plazo",
            duration=5,
        )

        assert deadline.type == "deadline"

    def test_deadline_timestamps_auto_generados(self):
        """created_at y updated_at deben auto-generarse."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Plazo",
            duration=5,
        )

        assert isinstance(deadline.created_at, datetime)
        assert isinstance(deadline.updated_at, datetime)

    def test_deadline_name_requerido(self):
        """name es un campo requerido."""
        with pytest.raises(ValidationError):
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                duration=5,
            )

    def test_deadline_duration_requerida(self):
        """duration es un campo requerido."""
        with pytest.raises(ValidationError):
            Deadline(
                partition_key="analysis-123",
                analysis_id="analysis-123",
                name="Plazo",
            )

    def test_deadline_soft_delete_flag(self):
        """Campo deleted debe existir para soft delete."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Plazo",
            duration=5,
            deleted=True,
        )

        assert deadline.deleted is True

    def test_deadline_serializacion_a_dict(self):
        """Deadline debe poder serializarse a dict para Cosmos."""
        deadline = Deadline(
            partition_key="analysis-123",
            analysis_id="analysis-123",
            name="Presentación de consultas",
            trigger_event_id="evt-1",
            duration=10,
            unit="días",
            day_type="hábiles",
            direccion="antes_de",
        )

        deadline_dict = deadline.model_dump()

        assert deadline_dict["type"] == "deadline"
        assert deadline_dict["name"] == "Presentación de consultas"
        assert deadline_dict["partition_key"] == "analysis-123"
        assert deadline_dict["calculation_status"] == "pending"
        assert deadline_dict["deleted"] is False
