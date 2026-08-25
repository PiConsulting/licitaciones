"""
Modelos de dominio para Timeline.

NO son modelos SQLAlchemy - solo estructuras para Cosmos DB.
Siguen el patrón de particionamiento por analysis_id.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


DateSource = Literal["detected", "user_input", "calculated", "pending"]
EventStatus = Literal["pending", "confirmed"]
DeadlineStatus = Literal["pending", "confirmed", "expired"]
PeriodType = Literal["calendar_days", "business_days"]


class Event(BaseModel):
    """
    Modelo de evento temporal en Cosmos DB.
    
    Los eventos representan hitos en el proceso de licitación que pueden
    tener fechas explícitas (detectadas, ingresadas o calculadas) o estar
    pendientes de asignación de fecha.
    
    Campos:
        id: Identificador único con formato "event::{uuid}"
        type: Discriminador fijo "event" para queries Cosmos
        partition_key: analysis_id para particionamiento eficiente
        analysis_id: ID del análisis al que pertenece el evento
        event_id: UUID del evento (sin prefijo)
        name: Nombre del evento (ej: "Apertura de Ofertas")
        event_date: Fecha del evento (None si está pendiente)
        date_source: Origen de la fecha (detected|user_input|calculated|pending)
        status: Estado del evento (pending|confirmed)
        source_document_id: ID del documento de origen (requerido si detected)
        source_page: Página del documento donde se detectó
        source_fragment: Fragmento de texto que evidencia el evento
        source_reference: Metadatos adicionales de la fuente
        deleted: Flag de soft delete
        created_at: Timestamp de creación
        updated_at: Timestamp de última actualización
    """
    
    id: str = Field(default_factory=lambda: f"event::{uuid4()}")
    type: Literal["event"] = "event"
    partition_key: str
    analysis_id: str
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    event_date: Optional[date] = None
    date_source: DateSource = "pending"
    status: EventStatus = "pending"
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    source_fragment: Optional[str] = None
    source_reference: Optional[dict[str, Any]] = None
    deleted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    @model_validator(mode="after")
    def validate_date_and_source_consistency(self) -> "Event":
        """
        Valida coherencia entre event_date y date_source.
        
        - Si event_date es None, date_source debe ser 'pending'
        - Si date_source es 'detected', debe existir source_document_id
        """
        if self.event_date is None and self.date_source != "pending":
            raise ValueError("Si event_date es null, date_source debe ser 'pending'")
        
        if self.date_source == "detected" and not self.source_document_id:
            raise ValueError("date_source='detected' requiere source_document_id")
        
        return self


class Deadline(BaseModel):
    """
    Modelo de plazo/deadline temporal en Cosmos DB.
    
    Los deadlines representan fechas límite que pueden ser explícitas
    (detectadas o ingresadas) o calculadas en base a plazos relativos
    desde otros eventos.
    
    Campos:
        id: Identificador único con formato "deadline::<uuid>"
        type: Discriminador fijo "deadline" para queries Cosmos
        partition_key: analysis_id para particionamiento eficiente
        analysis_id: ID del análisis al que pertenece el deadline
        deadline_id: UUID del deadline (sin prefijo)
        name: Nombre del deadline (ej: "Presentación de Ofertas")
        deadline_date: Fecha límite (None si está pendiente de cálculo)
        date_source: Origen de la fecha (detected|user_input|calculated|pending)
        status: Estado del deadline (pending|confirmed|expired)
        period_value: Cantidad de días para plazos relativos (ej: 5)
        period_type: Tipo de días (calendar_days|business_days)
        reference_event_id: ID del evento desde el cual se calcula
        source_document_id: ID del documento de origen
        source_page: Página del documento donde se detectó
        source_fragment: Fragmento de texto que evidencia el deadline
        source_reference: Metadatos adicionales de la fuente
        deleted: Flag de soft delete
        created_at: Timestamp de creación
        updated_at: Timestamp de última actualización
    """
    
    id: str = Field(default_factory=lambda: f"deadline::{uuid4()}")
    type: Literal["deadline"] = "deadline"
    partition_key: str
    analysis_id: str
    deadline_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    deadline_date: Optional[date] = None
    date_source: DateSource = "pending"
    status: DeadlineStatus = "pending"
    period_value: Optional[int] = None
    period_type: Optional[PeriodType] = None
    reference_event_id: Optional[str] = None
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    source_fragment: Optional[str] = None
    source_reference: Optional[dict[str, Any]] = None
    deleted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    @model_validator(mode="after")
    def validate_deadline_consistency(self) -> "Deadline":
        """
        Valida coherencia del deadline.
        
        - Si deadline_date es None, date_source debe ser 'pending'
        - Si date_source es 'detected', debe existir source_document_id
        - Si date_source es 'calculated', debe tener period_value, period_type y reference_event_id
        """
        if self.deadline_date is None and self.date_source != "pending":
            raise ValueError("Si deadline_date es null, date_source debe ser 'pending'")
        
        if self.date_source == "detected" and not self.source_document_id:
            raise ValueError("date_source='detected' requiere source_document_id")
        
        if self.date_source == "calculated":
            if not self.period_value:
                raise ValueError("date_source='calculated' requiere period_value")
            if not self.period_type:
                raise ValueError("date_source='calculated' requiere period_type")
            if not self.reference_event_id:
                raise ValueError("date_source='calculated' requiere reference_event_id")
        
        return self

