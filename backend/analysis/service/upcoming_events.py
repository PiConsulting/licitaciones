from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from analysis.models import Analysis, AnalysisVersion, BusinessStatus
from analysis.service.listing import _extract_organism
from documents.models import Document
from timeline.models_orm import EventORM
from users.access import analysis_scope_filter

UPCOMING_EVENTS_WINDOW_DAYS = 15
ALERTABLE_BUSINESS_STATUSES = (
    BusinessStatus.EN_REVISION.value,
    BusinessStatus.PRESENTADA.value,
)


def list_upcoming_events(
    db: Session,
    *,
    user_id: str,
    days: int = UPCOMING_EVENTS_WINDOW_DAYS,
    today: date | None = None,
) -> list[dict]:
    start = today or datetime.now().astimezone().date()
    end = start + timedelta(days=days)

    events = (
        db.query(EventORM)
        .join(Analysis, Analysis.id == EventORM.analysis_id)
        .filter(
            analysis_scope_filter(db, user_id),
            Analysis.deleted_at.is_(None),
            Analysis.business_status.in_(ALERTABLE_BUSINESS_STATUSES),
            EventORM.deleted.is_(False),
            EventORM.hidden.is_(False),
            EventORM.event_date.is_not(None),
            EventORM.event_date >= start,
            EventORM.event_date <= end,
        )
        .order_by(EventORM.event_date, EventORM.created_at)
        .all()
    )
    if not events:
        return []

    nearest: dict[str, EventORM] = {}
    counts: dict[str, int] = {}
    for event in events:
        counts[event.analysis_id] = counts.get(event.analysis_id, 0) + 1
        nearest.setdefault(event.analysis_id, event)

    rows = (
        db.query(
            Analysis.id,
            Analysis.analysis_name,
            Analysis.business_status,
            Analysis.business_unit,
            Document.filename,
            AnalysisVersion.extracted_data,
        )
        .outerjoin(
            Document,
            (Document.analysis_id == Analysis.id)
            & Document.is_primary.is_(True)
            & Document.deleted_at.is_(None),
        )
        .outerjoin(AnalysisVersion, AnalysisVersion.id == Analysis.current_version_id)
        .filter(Analysis.id.in_(list(nearest)))
        .all()
    )
    meta = {row[0]: row for row in rows}

    items: list[dict] = []
    for analysis_id, event in nearest.items():
        _, analysis_name, business_status, business_unit, filename, extracted_data = meta.get(
            analysis_id, (None,) * 6
        )
        assert event.event_date is not None
        items.append(
            {
                "analysis_id": analysis_id,
                "analysis_name": analysis_name or filename,
                "organismo": _extract_organism(extracted_data),
                "business_status": business_status,
                "business_unit": business_unit,
                "event_id": event.id,
                "event_name": event.name,
                "event_date": event.event_date,
                "days_until": (event.event_date - start).days,
                "additional_events": counts[analysis_id] - 1,
            }
        )

    items.sort(key=lambda item: (item["event_date"], item["analysis_name"] or ""))
    return items
