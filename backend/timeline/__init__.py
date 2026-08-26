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
    # Models
    "Event",
    "Deadline",
    "DateSource",
    "EventStatus",
    "DurationUnit",
    "DayType",
    "DireccionTemporal",
    "CalculationStatus",
    # Schemas
    "EventCreateRequest",
    "EventUpdateRequest",
    "EventResponse",
    "EventListResponse",
    "DeadlineCreateRequest",
    "DeadlineUpdateRequest",
    "DeadlineResponse",
    "DeadlineListResponse",
    # Service
    "TimelineService",
    # Calculator (Épica 17)
    "calcular_dias_corridos",  # Cálculo de días calendario (incluye fines de semana)
    "calcular_dias_habiles",  # Cálculo de días hábiles (lun-vie, salta fines de semana)
    "calcular_fechas_cascada",  # Motor de recálculo en cascada con detección de ciclos
    "validar_plazo_antes_calculo",  # Validación pre-cálculo de deadlines
    # Exceptions - lanzadas por calculator cuando:
    # - ValidationError: datos inválidos (trigger faltante, unit no soportado, etc.)
    # - CircularDependencyError: dependencias circulares en grafo eventos/plazos
    "ValidationError",
    "CircularDependencyError",
]
