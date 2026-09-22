"""Módulo Timeline para gestión de eventos temporales y plazos."""

from timeline.models import (
    Deadline,
    Event,
    DateSource,
    EventStatus,
    DurationUnit,
    DayType,
    DireccionTemporal,
    CalculationStatus,
)
from timeline.schemas import (
    EventCreateRequest,
    EventUpdateRequest,
    EventResponse,
    EventListResponse,
    DeadlineCreateRequest,
    DeadlineUpdateRequest,
    DeadlineResponse,
    DeadlineListResponse,
)
from timeline.service import TimelineService
from timeline.calculator import (
    calcular_dias_corridos,
    calcular_dias_habiles,
    calcular_fechas_cascada,
    validar_plazo_antes_calculo,
    ValidationError,
    CircularDependencyError,
)

__all__ = [
    "Event",
    "Deadline",
    "DateSource",
    "EventStatus",
    "DurationUnit",
    "DayType",
    "DireccionTemporal",
    "CalculationStatus",
    "EventCreateRequest",
    "EventUpdateRequest",
    "EventResponse",
    "EventListResponse",
    "DeadlineCreateRequest",
    "DeadlineUpdateRequest",
    "DeadlineResponse",
    "DeadlineListResponse",
    "TimelineService",
    "calcular_dias_corridos",
    "calcular_dias_habiles",
    "calcular_fechas_cascada",
    "validar_plazo_antes_calculo",
    "ValidationError",
    "CircularDependencyError",
]
