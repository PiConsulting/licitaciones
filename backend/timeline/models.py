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

# Vocabulario compartido con el extractor de la Story 15.2
# (backend/analysis/extraction/prompts/plazos_relativos.txt y
# PlazoRelativoExtracted en analysis/extraction/schemas.py). Se usa el mismo
# literal a propósito: un mapeo directo extracción -> Deadline no debe tener
# que traducir vocabulario, que es justo la clase de bug que ya rompió los
# prompts de la Épica 15 dos veces (clave raíz de JSON desalineada).
DurationUnit = Literal["días", "meses", "años", "horas"]
DayType = Literal["corridos", "hábiles", "no_especificado"]
DireccionTemporal = Literal["desde", "hasta", "antes_de", "después_de"]
CalculationStatus = Literal["pending", "calculated", "error"]


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
        - Si event_date no es None, date_source NO puede ser 'pending'
        - Si date_source es 'detected', debe existir source_document_id
        - partition_key debe ser igual a analysis_id
        """
        if self.event_date is None and self.date_source != "pending":
            raise ValueError("Si event_date es null, date_source debe ser 'pending'")
        
        if self.event_date is not None and self.date_source == "pending":
            raise ValueError("Si event_date tiene valor, date_source no puede ser 'pending'")
        
        if self.date_source == "detected" and not self.source_document_id:
            raise ValueError("date_source='detected' requiere source_document_id")
        
        if self.partition_key != self.analysis_id:
            raise ValueError("partition_key debe ser igual a analysis_id")
        
        return self


class Deadline(BaseModel):
    """
    Modelo de plazo relativo (deadline) en Cosmos DB.

    Un deadline vincula un evento disparador (trigger_event_id) con el
    evento resultado que produce (target_event_id), junto con la duración y
    el tipo de día con que se cuenta el plazo. El LLM (Story 15.2) NUNCA
    calcula la fecha: extrae esta estructura y la persiste con
    calculation_status="pending"; la fecha la completa el motor de cálculo
    determinístico (Epic 17), o un usuario a mano.

    Campos:
        id: Identificador único con formato "deadline::<uuid>"
        type: Discriminador fijo "deadline" para queries Cosmos
        partition_key: analysis_id para particionamiento eficiente
        analysis_id: ID del análisis al que pertenece el deadline
        deadline_id: UUID del deadline (sin prefijo)
        name: Descripción del plazo (ej: "Presentación de consultas")
        trigger_event_id: event_id del evento desde/hasta el cual se cuenta
            el plazo (equivalente a evento_disparador en la extracción).
            Puede ser None si todavía no se resolvió contra la lista de
            eventos del análisis -- la integridad referencial ("debe
            apuntar a un Event existente") la valida la capa de
            persistencia (Story 16.3), no este modelo.
        target_event_id: event_id del evento resultado que produce este
            plazo, si ya se identificó como tal. Puede ser None por el
            mismo motivo que trigger_event_id.
        duration: Cantidad de unidades de tiempo (ej. 45). Puede ser 0
            (ej. "a continuación de la emisión de la orden", sin cantidad
            explícita) -- por eso usa >=0 y no >0.
        unit: Unidad de tiempo (días|meses|años|horas)
        day_type: Tipo de día si unit="días" (corridos|hábiles|
            no_especificado). "no_especificado" es un valor legítimo y
            frecuente: el prompt de extracción tiene la regla explícita de
            NO asumir corridos/hábiles cuando el pliego no lo dice.
        direccion: Dirección temporal respecto al evento disparador
            (desde|hasta|antes_de|después_de)
        es_plazo_maximo: True si es un límite/deadline obligatorio, False
            si es una duración estimada o de ejecución
        deadline_date: Fecha calculada (None si está pendiente de cálculo)
        calculation_status: Estado del cálculo (pending|calculated|error)
        calculation_error: Mensaje de error si calculation_status="error"
            (ej. dependencia circular, evento disparador sin fecha aún)
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

        - Si deadline_date es None, calculation_status debe ser 'pending' o 'error'
        - Si calculation_status es 'calculated', debe existir deadline_date
        - Si calculation_status es 'error', debe existir calculation_error
        """
        if self.deadline_date is None and self.calculation_status == "calculated":
            raise ValueError("No puede estar 'calculated' sin deadline_date")

        if self.deadline_date is not None and self.calculation_status == "pending":
            raise ValueError(
                "Si hay deadline_date, calculation_status no puede quedar en 'pending'"
            )

        if self.calculation_status == "error" and not self.calculation_error:
            raise ValueError("calculation_status='error' requiere calculation_error")

        return self

