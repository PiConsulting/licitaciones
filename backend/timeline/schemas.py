"""
Schemas Pydantic para API REST de Timeline.

Schemas de request/response para endpoints de eventos y deadlines.
Separados de los modelos de dominio (timeline.models) para permitir
diferentes representaciones en API vs persistencia.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from timeline.models import (
    DateSource,
    EventStatus,
    DurationUnit,
    DayType,
    DireccionTemporal,
    CalculationStatus,
)


# ==================== EVENT SCHEMAS ====================

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
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    """Response para lista de eventos."""
    
    events: list[EventResponse]
    total: int


# ==================== DEADLINE SCHEMAS ====================

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
