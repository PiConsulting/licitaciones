"""Capa de acceso a datos de Timeline contra PostgreSQL.

Convierte entre las filas `EventORM`/`DeadlineORM` (persistencia) y los
modelos Pydantic `Event`/`Deadline` (dominio/API, `timeline/models.py`, sin
cambios). El `id` con prefijo tipo Cosmos (`"event::<uuid>"`) se preserva
solo en la capa Pydantic -- la fila SQL usa el uuid pelado como PK.
"""
from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from timeline.models import Deadline, Event
from timeline.models_orm import DeadlineORM, EventORM

# ==================== EVENTS ====================


def _event_to_pydantic(row: EventORM) -> Event:
    return Event(
        id=f"event::{row.id}",
        partition_key=row.analysis_id,
        analysis_id=row.analysis_id,
        event_id=row.id,
        name=row.name,
        event_date=row.event_date,
        date_source=row.date_source,
        status=row.status,
        source_document_id=row.source_document_id,
        source_page=row.source_page,
        source_fragment=row.source_fragment,
        source_reference=row.source_reference,
        deleted=row.deleted,
        hidden=row.hidden,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_event(db: Session, event: Event) -> Event:
    row = EventORM(
        id=event.event_id,
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
        hidden=event.hidden,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _event_to_pydantic(row)


def get_event(db: Session, event_id: str, analysis_id: str) -> Event | None:
    row = (
        db.query(EventORM)
        .filter(EventORM.id == event_id, EventORM.analysis_id == analysis_id)
        .first()
    )
    return _event_to_pydantic(row) if row is not None else None


def update_event(db: Session, event: Event) -> Event:
    row = db.query(EventORM).filter(EventORM.id == event.event_id).first()
    if row is None:
        raise NoResultFound(f"Event {event.event_id} not found")

    row.name = event.name
    row.event_date = event.event_date
    row.date_source = event.date_source
    row.status = event.status
    row.source_document_id = event.source_document_id
    row.source_page = event.source_page
    row.source_fragment = event.source_fragment
    row.source_reference = event.source_reference
    row.deleted = event.deleted
    row.hidden = event.hidden
    row.updated_at = event.updated_at
    db.commit()
    db.refresh(row)
    return _event_to_pydantic(row)


def list_events(
    db: Session,
    analysis_id: str,
    *,
    include_deleted: bool = False,
    include_hidden: bool = False,
    limit: int | None = None,
    skip: int = 0,
) -> list[Event]:
    query = db.query(EventORM).filter(EventORM.analysis_id == analysis_id)
    if not include_deleted:
        query = query.filter(EventORM.deleted.is_(False))
    if not include_hidden:
        query = query.filter(EventORM.hidden.is_(False))
    query = query.order_by(desc(EventORM.created_at))
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return [_event_to_pydantic(row) for row in query.all()]


# ==================== DEADLINES ====================


def _deadline_to_pydantic(row: DeadlineORM) -> Deadline:
    return Deadline(
        id=f"deadline::{row.id}",
        partition_key=row.analysis_id,
        analysis_id=row.analysis_id,
        deadline_id=row.id,
        name=row.name,
        trigger_event_id=row.trigger_event_id,
        target_event_id=row.target_event_id,
        duration=row.duration,
        unit=row.unit,
        day_type=row.day_type,
        direccion=row.direccion,
        es_plazo_maximo=row.es_plazo_maximo,
        deadline_date=row.deadline_date,
        calculation_status=row.calculation_status,
        calculation_error=row.calculation_error,
        source_document_id=row.source_document_id,
        source_page=row.source_page,
        source_fragment=row.source_fragment,
        source_reference=row.source_reference,
        deleted=row.deleted,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_deadline(db: Session, deadline: Deadline) -> Deadline:
    row = DeadlineORM(
        id=deadline.deadline_id,
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
    db.add(row)
    db.commit()
    db.refresh(row)
    return _deadline_to_pydantic(row)


def get_deadline(db: Session, deadline_id: str, analysis_id: str) -> Deadline | None:
    row = (
        db.query(DeadlineORM)
        .filter(DeadlineORM.id == deadline_id, DeadlineORM.analysis_id == analysis_id)
        .first()
    )
    return _deadline_to_pydantic(row) if row is not None else None


def update_deadline(db: Session, deadline: Deadline) -> Deadline:
    row = db.query(DeadlineORM).filter(DeadlineORM.id == deadline.deadline_id).first()
    if row is None:
        raise NoResultFound(f"Deadline {deadline.deadline_id} not found")

    row.name = deadline.name
    row.trigger_event_id = deadline.trigger_event_id
    row.target_event_id = deadline.target_event_id
    row.duration = deadline.duration
    row.unit = deadline.unit
    row.day_type = deadline.day_type
    row.direccion = deadline.direccion
    row.es_plazo_maximo = deadline.es_plazo_maximo
    row.deadline_date = deadline.deadline_date
    row.calculation_status = deadline.calculation_status
    row.calculation_error = deadline.calculation_error
    row.source_document_id = deadline.source_document_id
    row.source_page = deadline.source_page
    row.source_fragment = deadline.source_fragment
    row.source_reference = deadline.source_reference
    row.deleted = deadline.deleted
    row.updated_at = deadline.updated_at
    db.commit()
    db.refresh(row)
    return _deadline_to_pydantic(row)


def list_deadlines(
    db: Session,
    analysis_id: str,
    *,
    include_deleted: bool = False,
    limit: int | None = None,
    skip: int = 0,
) -> list[Deadline]:
    query = db.query(DeadlineORM).filter(DeadlineORM.analysis_id == analysis_id)
    if not include_deleted:
        query = query.filter(DeadlineORM.deleted.is_(False))
    query = query.order_by(desc(DeadlineORM.created_at))
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return [_deadline_to_pydantic(row) for row in query.all()]
