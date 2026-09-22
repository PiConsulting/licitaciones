"""
Schemas Pydantic para API REST de Timeline.

Schemas de request/response para endpoints de eventos y deadlines.
Separados de los modelos de dominio (timeline.models) para permitir
diferentes representaciones en API vs persistencia.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from timeline.models import (
    DateSource,
    EventStatus,
    DurationUnit,
    DayType,
    DireccionTemporal,
    CalculationStatus,
)


class EventCreateRequest(BaseModel):
    """Request para crear un evento."""
    
    name: str = Field(min_length=3, max_length=120)
    event_date: Optional[date] = None
    date_source: DateSource = "pending"
    status: EventStatus = "pending"
    source_document_id: Optional[str] = None
    source_page: Optional[int] = Field(None, ge=1)
    source_fragment: Optional[str] = Field(None, max_length=500)
    source_reference: Optional[dict] = None

    @model_validator(mode='after')
    def validate_date_source_consistency(self) -> 'EventCreateRequest':
        """F3 fix: Validar consistencia entre date_source y event_date."""
        if self.date_source == 'user_input' and not self.event_date:
            raise ValueError("date_source='user_input' requiere event_date")
        if self.date_source == 'pending' and self.event_date:
            raise ValueError("date_source='pending' es incompatible con event_date")
        return self


class EventUpdateRequest(BaseModel):
    """Request para actualizar un evento."""
    
    name: Optional[str] = Field(None, min_length=3, max_length=120)
    event_date: Optional[date] = None
    date_source: Optional[DateSource] = None
    status: Optional[EventStatus] = None
    source_document_id: Optional[str] = None
    source_page: Optional[int] = Field(None, ge=1)
    source_fragment: Optional[str] = Field(None, max_length=500)
    source_reference: Optional[dict] = None

    @model_validator(mode='after')
    def check_at_least_one_field(self) -> 'EventUpdateRequest':
        """F10 fix: Rechazar PATCH vacío - al menos un campo debe estar presente."""
        if all(v is None for v in self.model_dump().values()):
            raise ValueError("Al menos un campo debe ser proporcionado para actualizar")
        return self

    @model_validator(mode='after')
    def validate_date_source_consistency(self) -> 'EventUpdateRequest':
        """F3 fix: Validar consistencia entre date_source y event_date."""
        if self.date_source is not None and self.event_date is not None:
            if self.date_source == 'user_input' and not self.event_date:
                raise ValueError("date_source='user_input' requiere event_date")
            if self.date_source == 'pending' and self.event_date:
                raise ValueError("date_source='pending' es incompatible con event_date")
        return self


class EventResponse(BaseModel):
    """Response de un evento."""
    
    id: str
    event_id: str
    analysis_id: str
    name: str
    event_date: Optional[date]
    date_source: DateSource
    status: EventStatus
    source_document_id: Optional[str]
    source_page: Optional[int]
    source_fragment: Optional[str]
    source_reference: Optional[dict] = None
    deleted: bool
    hidden: bool = False
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    """Response para lista de eventos."""

    events: list[EventResponse]
    total: int


class EventHideRequest(BaseModel):
    """Request para ocultar/mostrar un evento (2026-09-01) sin borrarlo.

    Endpoint dedicado (como el soft-delete) en vez de agregarlo a
    `EventUpdateRequest`, para que "ocultar" quede como una acción explícita
    y no se pise por accidente con una edición de otro campo.
    """

    hidden: bool


class DeadlineCreateRequest(BaseModel):
    """Request para crear un deadline."""

    name: str = Field(min_length=3, max_length=120)
    trigger_event_id: Optional[str] = None
    target_event_id: Optional[str] = None
    duration: int = Field(ge=0)
    unit: DurationUnit = "días"
    day_type: DayType = "no_especificado"
    direccion: Optional[DireccionTemporal] = None
    es_plazo_maximo: bool = False
    deadline_date: Optional[date] = None
    calculation_status: CalculationStatus = "pending"
    calculation_error: Optional[str] = None
    source_document_id: Optional[str] = None
    source_page: Optional[int] = Field(None, ge=1)
    source_fragment: Optional[str] = Field(None, max_length=500)
    source_reference: Optional[dict] = None


class DeadlineUpdateRequest(BaseModel):
    """Request para actualizar un deadline."""

    name: Optional[str] = Field(None, min_length=3, max_length=120)
    trigger_event_id: Optional[str] = None
    target_event_id: Optional[str] = None
    duration: Optional[int] = Field(None, ge=0)
    unit: Optional[DurationUnit] = None
    day_type: Optional[DayType] = None
    direccion: Optional[DireccionTemporal] = None
    es_plazo_maximo: Optional[bool] = None
    deadline_date: Optional[date] = None
    calculation_status: Optional[CalculationStatus] = None
    calculation_error: Optional[str] = None
    source_document_id: Optional[str] = None
    source_page: Optional[int] = Field(None, ge=1)
    source_fragment: Optional[str] = Field(None, max_length=500)
    source_reference: Optional[dict] = None


class DeadlineResponse(BaseModel):
    """Response de un deadline."""

    id: str
    deadline_id: str
    analysis_id: str
    name: str
    trigger_event_id: Optional[str]
    target_event_id: Optional[str]
    duration: int
    unit: DurationUnit
    day_type: DayType
    direccion: Optional[DireccionTemporal]
    es_plazo_maximo: bool
    deadline_date: Optional[date]
    calculation_status: CalculationStatus
    calculation_error: Optional[str]
    source_document_id: Optional[str]
    source_page: Optional[int]
    source_fragment: Optional[str]
    source_reference: Optional[dict] = None
    deleted: bool
    created_at: datetime
    updated_at: datetime


class DeadlineListResponse(BaseModel):
    """Response para lista de deadlines."""
    
    deadlines: list[DeadlineResponse]
    total: int
