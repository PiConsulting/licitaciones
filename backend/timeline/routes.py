"""
Router de FastAPI para Timeline.

Endpoints REST para gestionar eventos y deadlines del timeline.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from infra.database import get_db
from timeline.service import TimelineService
from timeline.schemas import EventCreateRequest, EventUpdateRequest, EventHideRequest
from timeline.models import Event
from timeline.calculation_engine import recalculate_dependent_dates
from users.service import get_current_user, http_bearer

timeline_router = APIRouter(prefix="/analyses/{analysis_id}/timeline", tags=["timeline"])


@timeline_router.get("/events")
def get_timeline_events(
    analysis_id: str,
    include_deleted: bool = False,
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Obtiene todos los eventos del timeline para un análisis.

    Args:
        analysis_id: ID del análisis
        include_deleted: Si True, incluye eventos marcados como deleted
        include_hidden: Si True, incluye eventos marcados como hidden (ver
            `Event.hidden`) -- el frontend lo pide con True siempre y filtra
            del lado del cliente según el toggle "Mostrar ocultos", para no
            perder de vista cuáles existen mientras decide qué mostrar
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Lista de eventos

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)
    events = service.list_events(
        analysis_id,
        current_user.id,
        include_deleted=include_deleted,
        include_hidden=include_hidden,
    )

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
            "hidden": event.hidden,
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


@timeline_router.post("/events", status_code=status.HTTP_201_CREATED)
def create_timeline_event(
    analysis_id: str,
    event_data: EventCreateRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Crea un nuevo evento en el timeline.

    Args:
        analysis_id: ID del análisis
        event_data: Datos del evento a crear
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Evento creado

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)

    # Construir modelo de dominio Event
    event = Event(
        partition_key=analysis_id,
        analysis_id=analysis_id,
        name=event_data.name,
        event_date=event_data.event_date,
        date_source=event_data.date_source,
        status=event_data.status,
        source_document_id=event_data.source_document_id,
        source_page=event_data.source_page,
        source_fragment=event_data.source_fragment,
        source_reference=event_data.source_reference,
    )

    # Persistir
    created_event = service.create_event(event, current_user.id)

    # Mapeo a formato que espera frontend
    return {
        "id": created_event.id,
        "event_id": created_event.event_id,
        "analysis_id": created_event.analysis_id,
        "name": created_event.name,
        "event_date": created_event.event_date.isoformat() if created_event.event_date else None,
        "date_source": created_event.date_source,
        "status": created_event.status,
        "source_document_id": created_event.source_document_id,
        "source_page": created_event.source_page,
        "source_fragment": created_event.source_fragment,
        "source_reference": created_event.source_reference,
        "deleted": created_event.deleted,
        "hidden": created_event.hidden,
        "created_at": created_event.created_at.isoformat(),
        "updated_at": created_event.updated_at.isoformat(),
    }


@timeline_router.patch("/events/{event_id}")
def update_timeline_event(
    analysis_id: str,
    event_id: str,
    event_data: EventUpdateRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Actualiza un evento existente del timeline.

    Args:
        analysis_id: ID del análisis
        event_id: ID del evento a actualizar
        event_data: Datos a actualizar
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Evento actualizado

    Raises:
        HTTPException: 404 si análisis o evento no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)

    # Obtener evento existente
    existing_event = service.get_event(event_id, analysis_id, current_user.id)
    if not existing_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento {event_id} no encontrado"
        )

    # Actualizar campos proporcionados
    if event_data.name is not None:
        existing_event.name = event_data.name
    if event_data.event_date is not None:
        existing_event.event_date = event_data.event_date
    if event_data.date_source is not None:
        existing_event.date_source = event_data.date_source
    if event_data.status is not None:
        existing_event.status = event_data.status
    if event_data.source_document_id is not None:
        existing_event.source_document_id = event_data.source_document_id
    if event_data.source_page is not None:
        existing_event.source_page = event_data.source_page
    if event_data.source_fragment is not None:
        existing_event.source_fragment = event_data.source_fragment
    if event_data.source_reference is not None:
        existing_event.source_reference = event_data.source_reference

    # Persistir actualización
    updated_event = service.update_event(existing_event, current_user.id)

    # Mapeo a formato que espera frontend
    return {
        "id": updated_event.id,
        "event_id": updated_event.event_id,
        "analysis_id": updated_event.analysis_id,
        "name": updated_event.name,
        "event_date": updated_event.event_date.isoformat() if updated_event.event_date else None,
        "date_source": updated_event.date_source,
        "status": updated_event.status,
        "source_document_id": updated_event.source_document_id,
        "source_page": updated_event.source_page,
        "source_fragment": updated_event.source_fragment,
        "source_reference": updated_event.source_reference,
        "deleted": updated_event.deleted,
        "hidden": updated_event.hidden,
        "created_at": updated_event.created_at.isoformat(),
        "updated_at": updated_event.updated_at.isoformat(),
    }


@timeline_router.patch("/events/{event_id}/hide")
def set_timeline_event_hidden(
    analysis_id: str,
    event_id: str,
    hide_data: EventHideRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Oculta o muestra un evento del timeline sin borrarlo (2026-09-01).

    Distinto del soft-delete: el evento sigue existiendo y se sigue usando
    con normalidad para calcular fechas de otros eventos que dependan de él
    -- solo deja de contar en las estadísticas del timeline y en el panel de
    "fechas por cargar" mientras está oculto. Pensado para eventos que el
    pliego menciona pero no son relevantes en el momento actual del proceso
    (ej. "Notificación de fuerza mayor"), sin perder trazabilidad.

    Args:
        analysis_id: ID del análisis
        event_id: ID del evento a ocultar/mostrar
        hide_data: `{"hidden": true|false}`
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Evento actualizado

    Raises:
        HTTPException: 404 si evento no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)

    updated_event = service.set_event_hidden(
        event_id=event_id,
        analysis_id=analysis_id,
        user_id=current_user.id,
        hidden=hide_data.hidden,
    )

    if not updated_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento {event_id} no encontrado",
        )

    return {
        "id": updated_event.id,
        "event_id": updated_event.event_id,
        "analysis_id": updated_event.analysis_id,
        "name": updated_event.name,
        "event_date": updated_event.event_date.isoformat() if updated_event.event_date else None,
        "date_source": updated_event.date_source,
        "status": updated_event.status,
        "source_document_id": updated_event.source_document_id,
        "source_page": updated_event.source_page,
        "source_fragment": updated_event.source_fragment,
        "source_reference": updated_event.source_reference,
        "deleted": updated_event.deleted,
        "hidden": updated_event.hidden,
        "created_at": updated_event.created_at.isoformat(),
        "updated_at": updated_event.updated_at.isoformat(),
    }


@timeline_router.post("/events/{event_id}/recalculate")
def recalculate_event_dependents(
    analysis_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Recalcula fechas de todos los eventos que dependen del evento especificado.

    Args:
        analysis_id: ID del análisis
        event_id: ID del evento trigger
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Estadísticas del recálculo (events_updated, errors)

    Raises:
        HTTPException: 404 si análisis no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)

    # Ejecutar recálculo en cascada
    result = recalculate_dependent_dates(
        service=service,
        analysis_id=analysis_id,
        event_id=event_id,
        user_id=current_user.id
    )

    # F5 fix: Return 207 Multi-Status if there are partial errors
    from fastapi.responses import JSONResponse
    
    response_data = {
        "events_updated": result.events_updated,
        "errors": result.errors
    }
    
    if result.errors and len(result.errors) > 0:
        return JSONResponse(
            content=response_data,
            status_code=207  # Multi-Status for partial success
        )
    
    return response_data


@timeline_router.delete("/events/{event_id}")
def delete_timeline_event(
    analysis_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Soft-delete de un evento (marca deleted=True).

    Args:
        analysis_id: ID del análisis
        event_id: ID del evento a eliminar
        db: Sesión de base de datos
        credentials: Credenciales JWT del usuario autenticado

    Returns:
        Mensaje de confirmación

    Raises:
        HTTPException: 404 si evento no existe, 403 si no es owner
    """
    current_user = get_current_user(credentials, None)
    service = TimelineService(db)

    # Ejecutar soft-delete
    success = service.delete_event(
        event_id=event_id,
        analysis_id=analysis_id,
        user_id=current_user.id
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Evento no encontrado"
        )

    return {
        "message": "Evento eliminado correctamente",
        "event_id": event_id
    }
