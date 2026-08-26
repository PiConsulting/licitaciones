"""Entrypoint de tracking: iniciar, leer y completar el tracking de un analisis. Compone storage + serialization + categories + comments."""
from __future__ import annotations

from uuid import uuid4

from azure.cosmos.exceptions import CosmosAccessConditionFailedError

from tracking.service.categories import _build_default_categories
from tracking.service.comments import _resolve_user_display_name
from tracking.service.serialization import _to_tracking_payload
from tracking.service.storage import (
    _load_analysis_or_raise,
    _load_latest_version,
    _read_tracking_or_none,
    _save_tracking_with_etag,
    _tracking_id,
)
from tracking.service.utils import _now_iso


def start_tracking(analysis_id: str, user_id: str) -> dict:
    analysis = _load_analysis_or_raise(analysis_id, user_id)
    if analysis.get("status") not in {"analyzed", "validated"}:
        raise RuntimeError("TRACKING_NOT_AVAILABLE")

    version = _load_latest_version(analysis_id)
    version_id = str(version.get("version_id") or "")
    if not version_id:
        raise ValueError("NO_VERSION_YET")

    existing = _read_tracking_or_none(analysis_id, version_id)
    if existing is not None:
        if str(existing.get("status") or "active") == "completed":
            now = _now_iso()
            existing["status"] = "active"
            existing["updated_at"] = now
            events = existing.get("events") if isinstance(existing.get("events"), list) else []
            events.append(
                {
                    "id": f"tracking_event::{uuid4()}",
                    "event": "tracking_resumed",
                    "at": now,
                    "by": user_id,
                }
            )
            existing["events"] = events
            try:
                _save_tracking_with_etag(existing)
            except CosmosAccessConditionFailedError as exc:
                raise RuntimeError("TRACKING_CONFLICT") from exc
        return _to_tracking_payload(existing)

    now = _now_iso()
    tracking = {
        "id": _tracking_id(analysis_id, version_id),
        "type": "tracking",
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "version_id": version_id,
        "status": "active",
        "started_by": user_id,
        "started_at": now,
        "updated_at": now,
        "categories": _build_default_categories(
            version_id=version_id, extracted_data=version.get("extracted_data") or {}
        ),
    }
    _save_tracking_with_etag(tracking)
    return _to_tracking_payload(tracking)


def get_tracking(analysis_id: str, user_id: str) -> dict | None:
    analysis = _load_analysis_or_raise(analysis_id, user_id)
    version_id = str(analysis.get("current_version_id") or "")
    if not version_id:
        return None
    tracking = _read_tracking_or_none(analysis_id, version_id)
    if tracking is None:
        return None
    return _to_tracking_payload(tracking)


def complete_tracking(
    analysis_id: str, user_id: str, *, completed_by_name: str | None = None
) -> dict:
    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    raw = _read_tracking_or_none(analysis_id, str(tracking["version_id"]))
    if raw is None:
        raise ValueError("TRACKING_NOT_FOUND")

    if str(raw.get("status") or "active") == "completed":
        return _to_tracking_payload(raw)

    now = _now_iso()
    raw["status"] = "completed"
    raw["completed_by"] = user_id
    raw["completed_by_name"] = (completed_by_name or "").strip() or _resolve_user_display_name(
        user_id
    )
    raw["completed_at"] = now
    raw["updated_at"] = now
    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    events.append(
        {
            "id": f"tracking_event::{uuid4()}",
            "event": "tracking_completed",
            "at": now,
            "by": user_id,
        }
    )
    raw["events"] = events

    try:
        _save_tracking_with_etag(raw)
    except CosmosAccessConditionFailedError as exc:
        raise RuntimeError("TRACKING_CONFLICT") from exc

    return _to_tracking_payload(raw)
