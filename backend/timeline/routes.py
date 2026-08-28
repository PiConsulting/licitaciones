"""
Router de FastAPI para Timeline.

Endpoints REST para gestionar eventos y deadlines del timeline.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from infra.database import get_db
from timeline.schemas import EventResponse, DeadlineResponse
from timeline.service import TimelineService
from users.dependencies import get_current_user_id

timeline_router = APIRouter(prefix="/analyses/{analysis_id}/timeline", tags=["timeline"])


@timeline_router.get("/events", response_model=list[EventResponse])
def get_timeline_events(
    analysis_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Obtiene todos los eventos del timeline para un análisis.

    Args:
        analysis_id: ID del análisis
        include_deleted: Si True, incluye eventos marcados como deleted
        db: Sesión de base de datos
        user_id: ID del usuario autenticado

    Returns:
        Lista de eventos

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    service = TimelineService(db)
    events = service.list_events(analysis_id, user_id, include_deleted=include_deleted)

    # Convertir modelos Event a EventResponse
    return [
        EventResponse(
            id=event.id,
            event_id=event.event_id,
            analysis_id=event.analysis_id,
            name=event.name,
            event_date=event.event_date,
            date_source=event.date_source,
            status=event.status,
            source_document_id=event.source_document_id,
            source_page=event.source_page,
            source_fragment=event.source_fragment,
            source_reference=event.source_reference,
            deleted=event.deleted,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )
        for event in events
    ]


@timeline_router.get("/deadlines", response_model=list[DeadlineResponse])
def get_timeline_deadlines(
    analysis_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Obtiene todos los deadlines del timeline para un análisis.

    Args:
        analysis_id: ID del análisis
        include_deleted: Si True, incluye deadlines marcados como deleted
        db: Sesión de base de datos
        user_id: ID del usuario autenticado

    Returns:
        Lista de deadlines

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    service = TimelineService(db)
    deadlines = service.list_deadlines(analysis_id, user_id, include_deleted=include_deleted)

    # Convertir modelos Deadline a DeadlineResponse
    return [
        DeadlineResponse(
            id=deadline.id,
            deadline_id=deadline.deadline_id,
            analysis_id=deadline.analysis_id,
            name=deadline.name,
            trigger_event_id=deadline.trigger_event_id,
            target_event_id=deadline.target_event_id,
            duration=deadline.duration,
            unit=deadline.unit,
            day_type=deadline.day_type,
            direccion=deadline.direccion,
            es_plazo_maximo=deadline.es_plazo_maximo,
            deadline_date=deadline.deadline_date,
            calculation_status=deadline.calculation_status,
            calculation_error=deadline.calculation_error,
            source_document_id=deadline.source_document_id,
            source_page=deadline.source_page,
            source_fragment=deadline.source_fragment,
            source_reference=deadline.source_reference,
            deleted=deadline.deleted,
            created_at=deadline.created_at,
            updated_at=deadline.updated_at,
        )
        for deadline in deadlines
    ]
