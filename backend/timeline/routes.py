"""
Router de FastAPI para Timeline.

Endpoints REST para gestionar eventos y deadlines del timeline.
"""
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from infra.database import get_db
from timeline.service import TimelineService
from users.service import get_current_user, http_bearer

timeline_router = APIRouter(prefix="/analyses/{analysis_id}/timeline", tags=["timeline"])


@timeline_router.get("/events")
def get_timeline_events(
    analysis_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Obtiene todos los eventos del timeline para un análisis.

    Args:
        analysis_id: ID del análisis
        include_deleted: Si True, incluye eventos marcados como deleted
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Lista de eventos

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)
    events = service.list_events(analysis_id, current_user.id, include_deleted=include_deleted)

    # Mapeo manual a formato que espera frontend
    return [
        {
            "id": event.id,
            "event_id": event.event_id,
            "analysis_id": event.analysis_id,
            "name": event.name,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "date_source": event.date_source,
            "status": event.status,
            "source_document_id": event.source_document_id,
            "source_page": event.source_page,
            "source_fragment": event.source_fragment,
            "source_reference": event.source_reference,
            "deleted": event.deleted,
            "created_at": event.created_at.isoformat(),
            "updated_at": event.updated_at.isoformat(),
        }
        for event in events
    ]


@timeline_router.get("/deadlines")
def get_timeline_deadlines(
    analysis_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Obtiene todos los deadlines del timeline para un análisis.

    Args:
        analysis_id: ID del análisis
        include_deleted: Si True, incluye deadlines marcados como deleted
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Lista de deadlines

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)
    deadlines = service.list_deadlines(analysis_id, current_user.id, include_deleted=include_deleted)

    # Mapeo manual a formato que espera frontend
    return [
        {
            "id": deadline.id,
            "deadline_id": deadline.deadline_id,
            "analysis_id": deadline.analysis_id,
            "target_event_id": deadline.target_event_id,
            "trigger_event_id": deadline.trigger_event_id,
            "duration": deadline.duration,
            "unit": deadline.unit,
            "day_type": deadline.day_type,
            "calculated_date": deadline.deadline_date.isoformat() if deadline.deadline_date else None,
            "calculation_status": deadline.calculation_status,
            "calculation_error": deadline.calculation_error,
            "source_document_id": deadline.source_document_id,
            "source_page": deadline.source_page,
            "deleted": deadline.deleted,
            "created_at": deadline.created_at.isoformat(),
            "updated_at": deadline.updated_at.isoformat(),
        }
        for deadline in deadlines
    ]
