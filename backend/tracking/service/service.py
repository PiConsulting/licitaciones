"""Entrypoint de tracking: iniciar, leer y completar el tracking de un
analisis. Compone storage + serialization + categories + comments.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from infra.database import SessionLocal
from tracking.models import Tracking
from tracking.service.categories import (
    _build_default_category_rows,
    ensure_tracking_active_or_raise,
)
from tracking.service.comments import _resolve_user_display_name
from tracking.service.serialization import _to_tracking_payload
from tracking.service.storage import (
    _apply_tracking_cas_update,
    _load_analysis_or_raise,
    _load_latest_version,
    _read_tracking_or_none,
)


def _load_active_tracking_for_user(db: Session, analysis_id: str, user_id: str) -> Tracking:
    """Valida ownership del análisis + trae el tracking de la versión
    actual, o levanta si no existe / está completado (read-only). Usada por
    categories.py/comments.py para no repetir esta secuencia."""
    analysis = _load_analysis_or_raise(db, analysis_id, user_id)
    version_id = str(analysis.current_version_id or "")
    if not version_id:
        raise ValueError("TRACKING_NOT_FOUND")
    tracking = _read_tracking_or_none(db, analysis_id, version_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")
    ensure_tracking_active_or_raise(tracking)
    return tracking


def start_tracking(analysis_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        analysis = _load_analysis_or_raise(db, analysis_id, user_id)
        if analysis.status not in {"analyzed", "validated"}:
            raise RuntimeError("TRACKING_NOT_AVAILABLE")

        version = _load_latest_version(db, analysis_id)
        version_id = version.id

        existing = _read_tracking_or_none(db, analysis_id, version_id)
        if existing is not None:
            if existing.status == "completed":
                now = datetime.now(UTC)
                existing.status = "active"
                events = list(existing.events or [])
                events.append(
                    {
                        "id": f"tracking_event::{uuid4()}",
                        "event": "tracking_resumed",
                        "at": now.isoformat(),
                        "by": user_id,
                    }
                )
                existing.events = events
                new_updated_at = _apply_tracking_cas_update(db, existing.id, existing.updated_at, now)
                existing.updated_at = new_updated_at
            return _to_tracking_payload(db, existing)

        now = datetime.now(UTC)
        tracking = Tracking(
            analysis_id=analysis_id,
            version_id=version_id,
            status="active",
            started_by=user_id,
            started_at=now,
            updated_at=now,
            categories=_build_default_category_rows(
                version_id=version_id, extracted_data=version.extracted_data or {}
            ),
        )
        db.add(tracking)
        db.commit()
        db.refresh(tracking)
        return _to_tracking_payload(db, tracking)
    finally:
        db.close()


def get_tracking(analysis_id: str, user_id: str) -> dict | None:
    db = SessionLocal()
    try:
        analysis = _load_analysis_or_raise(db, analysis_id, user_id)
        version_id = str(analysis.current_version_id or "")
        if not version_id:
            return None
        tracking = _read_tracking_or_none(db, analysis_id, version_id)
        if tracking is None:
            return None
        return _to_tracking_payload(db, tracking)
    finally:
        db.close()


def complete_tracking(
    analysis_id: str, user_id: str, *, completed_by_name: str | None = None
) -> dict:
    db = SessionLocal()
    try:
        analysis = _load_analysis_or_raise(db, analysis_id, user_id)
        version_id = str(analysis.current_version_id or "")
        if not version_id:
            raise ValueError("TRACKING_NOT_FOUND")
        tracking = _read_tracking_or_none(db, analysis_id, version_id)
        if tracking is None:
            raise ValueError("TRACKING_NOT_FOUND")

        if tracking.status == "completed":
            return _to_tracking_payload(db, tracking)

        now = datetime.now(UTC)
        tracking.status = "completed"
        tracking.completed_by = user_id
        tracking.completed_by_name = (
            completed_by_name or ""
        ).strip() or _resolve_user_display_name(db, user_id)
        tracking.completed_at = now
        events = list(tracking.events or [])
        events.append(
            {
                "id": f"tracking_event::{uuid4()}",
                "event": "tracking_completed",
                "at": now.isoformat(),
                "by": user_id,
            }
        )
        tracking.events = events

        new_updated_at = _apply_tracking_cas_update(db, tracking.id, tracking.updated_at, now)
        tracking.updated_at = new_updated_at
        return _to_tracking_payload(db, tracking)
    finally:
        db.close()
