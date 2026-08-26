"""Transiciones de estado de categoria/item del checklist de tracking."""
from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from azure.cosmos.exceptions import CosmosAccessConditionFailedError

from tracking.service.serialization import _to_tracking_payload
from tracking.service.storage import _read_tracking_or_none, _save_tracking_with_etag
from tracking.service.utils import (
    ACTIONABLE_CHECKLIST_CATEGORIES,
    TRACKING_CATEGORY_KEYS,
    _normalize_text,
    _now_iso,
)


def _build_default_categories(*, version_id: str, extracted_data: dict) -> dict:
    categories: dict[str, dict] = {}
    for key in TRACKING_CATEGORY_KEYS:
        cat = {
            "category_key": key,
            "status": "in_review",
            "updated_by": None,
            "updated_at": None,
            "closed_by": None,
            "closed_at": None,
            "reopened_by": None,
            "reopened_at": None,
            "items": [],
            "events": [],
        }
        if key in ACTIONABLE_CHECKLIST_CATEGORIES:
            cat["items"] = _extract_tracking_items_from_version(
                version_id=version_id,
                category_key=key,
                extracted_data=extracted_data,
            )
        categories[key] = cat
    return categories


def _extract_tracking_items_from_version(
    *, version_id: str, category_key: str, extracted_data: dict
) -> list[dict]:
    raw_items = extracted_data.get(category_key)
    if not isinstance(raw_items, list):
        return []
    items: list[dict] = []
    for idx, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        refs = (
            raw_item.get("source_references")
            if isinstance(raw_item.get("source_references"), list)
            else []
        )
        first_ref = refs[0] if refs and isinstance(refs[0], dict) else {}
        citation_text = str(first_ref.get("citation") or "")
        items.append(
            {
                "tracking_item_id": _build_tracking_item_id(
                    version_id=version_id,
                    category_key=category_key,
                    item=raw_item,
                    position=idx,
                ),
                "category_key": category_key,
                "source_item_ref": {
                    "version_id": version_id,
                    "field_name": str(raw_item.get("tipo") or f"item_{idx + 1}"),
                    "document_id": first_ref.get("document_id"),
                    "page": int(first_ref.get("page_number") or 0) if first_ref else None,
                    "citation_hash": sha256(citation_text.encode("utf-8")).hexdigest()[:16]
                    if citation_text
                    else None,
                },
                "status": "not_evaluated",
                "updated_by": None,
                "updated_at": None,
            }
        )
    return items


def _build_tracking_item_id(
    *, version_id: str, category_key: str, item: dict, position: int
) -> str:
    refs = item.get("source_references") if isinstance(item.get("source_references"), list) else []
    first_ref = refs[0] if refs and isinstance(refs[0], dict) else {}
    raw = "|".join(
        [
            version_id,
            category_key,
            _normalize_text(item.get("tipo")),
            _normalize_text(item.get("valor")),
            str(first_ref.get("document_id") or ""),
            str(first_ref.get("page_number") or ""),
            _normalize_text(first_ref.get("citation")),
            str(position),
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def _ensure_status_transition(current: str, target: str) -> None:
    allowed = {
        "not_reviewed": {"in_review", "closed"},
        "in_review": {"closed"},
        "closed": {"in_review"},
    }
    if target not in allowed.get(current, set()):
        raise ValueError("INVALID_TRACKING_TRANSITION")


def _get_category_or_raise(tracking: dict, category_key: str) -> dict:
    categories = tracking.get("categories") if isinstance(tracking.get("categories"), dict) else {}
    category = categories.get(category_key)
    if not isinstance(category, dict):
        raise ValueError("TRACKING_CATEGORY_NOT_FOUND")
    return category


def _ensure_category_not_closed(category: dict) -> None:
    if category.get("status") == "closed":
        raise RuntimeError("TRACKING_CATEGORY_CLOSED")


def ensure_tracking_active_or_raise(tracking: dict) -> None:
    if str(tracking.get("status") or "active") == "completed":
        raise RuntimeError("TRACKING_COMPLETED_READ_ONLY")


def update_category_status(
    analysis_id: str, user_id: str, category_key: str, target_status: str
) -> dict:
    # Import diferido: service importa _build_default_categories de este
    # módulo; importar get_tracking acá arriba crearía un ciclo.
    from tracking.service.service import get_tracking

    if category_key not in TRACKING_CATEGORY_KEYS:
        raise ValueError("TRACKING_CATEGORY_NOT_FOUND")
    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    raw = _read_tracking_or_none(analysis_id, str(tracking["version_id"]))
    if raw is None:
        raise ValueError("TRACKING_NOT_FOUND")
    ensure_tracking_active_or_raise(raw)

    categories = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    category = (
        categories.get(category_key) if isinstance(categories.get(category_key), dict) else None
    )
    if category is None:
        raise ValueError("TRACKING_CATEGORY_NOT_FOUND")

    current_status = str(category.get("status") or "not_reviewed")
    _ensure_status_transition(current_status, target_status)

    now = _now_iso()
    category["status"] = target_status
    category["updated_by"] = user_id
    category["updated_at"] = now
    if target_status == "closed":
        category["closed_by"] = user_id
        category["closed_at"] = now
    if current_status == "closed" and target_status == "in_review":
        category["reopened_by"] = user_id
        category["reopened_at"] = now

    events = category.get("events") if isinstance(category.get("events"), list) else []
    events.append(
        {
            "id": f"tracking_event::{uuid4()}",
            "event": "category_reopened"
            if (current_status == "closed" and target_status == "in_review")
            else "category_status_changed",
            "from": current_status,
            "to": target_status,
            "at": now,
            "by": user_id,
        }
    )
    category["events"] = events
    raw["updated_at"] = now

    try:
        _save_tracking_with_etag(raw)
    except CosmosAccessConditionFailedError as exc:
        raise RuntimeError("TRACKING_CONFLICT") from exc

    return _to_tracking_payload(raw)


def update_tracking_item_status(
    analysis_id: str,
    user_id: str,
    category_key: str,
    tracking_item_id: str,
    target_status: str,
) -> dict:
    from tracking.service.service import get_tracking

    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    raw = _read_tracking_or_none(analysis_id, str(tracking["version_id"]))
    if raw is None:
        raise ValueError("TRACKING_NOT_FOUND")
    ensure_tracking_active_or_raise(raw)

    category = _get_category_or_raise(raw, category_key)
    _ensure_category_not_closed(category)
    items = category.get("items") if isinstance(category.get("items"), list) else []
    target = None
    for item in items:
        if isinstance(item, dict) and str(item.get("tracking_item_id")) == tracking_item_id:
            target = item
            break
    if target is None:
        raise ValueError("TRACKING_ITEM_NOT_FOUND")

    now = _now_iso()
    target["status"] = target_status
    target["updated_by"] = user_id
    target["updated_at"] = now
    category["updated_by"] = user_id
    category["updated_at"] = now
    raw["updated_at"] = now

    try:
        _save_tracking_with_etag(raw)
    except CosmosAccessConditionFailedError as exc:
        raise RuntimeError("TRACKING_CONFLICT") from exc

    return _to_tracking_payload(raw)
