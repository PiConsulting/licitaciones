"""Transiciones de estado de categoria/item del checklist de tracking, y
construcción del checklist inicial a partir de la extracción."""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from tracking.models import Tracking, TrackingCategory, TrackingItem
from tracking.service.storage import _apply_tracking_cas_update
from tracking.service.utils import (
    ACTIONABLE_CHECKLIST_CATEGORIES,
    TRACKING_CATEGORY_KEYS,
    _normalize_text,
)


def _build_default_category_rows(
    *, version_id: str, extracted_data: dict
) -> list[TrackingCategory]:
    """Arma las filas `TrackingCategory`/`TrackingItem` (sin persistir
    todavía) para un tracking recién creado, a partir de la última versión
    extraída. Misma lógica de generación de ids que la versión Cosmos
    (`_build_tracking_item_id`, determinística) -- sólo cambia el shape de
    salida (filas ORM en vez de dicts para un doc anidado).
    """
    rows: list[TrackingCategory] = []
    for key in TRACKING_CATEGORY_KEYS:
        items: list[TrackingItem] = []
        if key in ACTIONABLE_CHECKLIST_CATEGORIES:
            items = _extract_tracking_items_from_version(
                version_id=version_id, category_key=key, extracted_data=extracted_data
            )
        rows.append(
            TrackingCategory(
                category_key=key,
                status="in_review",
                items=items,
            )
        )
    return rows


def _extract_tracking_items_from_version(
    *, version_id: str, category_key: str, extracted_data: dict
) -> list[TrackingItem]:
    raw_items = extracted_data.get(category_key)
    if not isinstance(raw_items, list):
        return []
    items: list[TrackingItem] = []
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
            TrackingItem(
                id=_build_tracking_item_id(
                    version_id=version_id, category_key=category_key, item=raw_item, position=idx
                ),
                status="not_evaluated",
                source_version_id=version_id,
                source_field_name=str(raw_item.get("tipo") or f"item_{idx + 1}"),
                source_document_id=first_ref.get("document_id"),
                source_page=int(first_ref.get("page_number") or 0) if first_ref else None,
                source_citation_hash=sha256(citation_text.encode("utf-8")).hexdigest()[:16]
                if citation_text
                else None,
            )
        )
    return items


def _build_tracking_item_id(*, version_id: str, category_key: str, item: dict, position: int) -> str:
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


def _get_category_row_or_raise(
    db: Session, tracking_id: str, category_key: str
) -> TrackingCategory:
    category = (
        db.query(TrackingCategory)
        .filter(TrackingCategory.tracking_id == tracking_id, TrackingCategory.category_key == category_key)
        .first()
    )
    if category is None:
        raise ValueError("TRACKING_CATEGORY_NOT_FOUND")
    return category


def _ensure_category_not_closed(category: TrackingCategory) -> None:
    if category.status == "closed":
        raise RuntimeError("TRACKING_CATEGORY_CLOSED")


def ensure_tracking_active_or_raise(tracking: Tracking) -> None:
    if tracking.status == "completed":
        raise RuntimeError("TRACKING_COMPLETED_READ_ONLY")


def update_category_status(
    analysis_id: str, user_id: str, category_key: str, target_status: str
) -> dict:
    from infra.database import SessionLocal
    from tracking.service.serialization import _to_tracking_payload
    from tracking.service.service import _load_active_tracking_for_user

    if category_key not in TRACKING_CATEGORY_KEYS:
        raise ValueError("TRACKING_CATEGORY_NOT_FOUND")

    db = SessionLocal()
    try:
        tracking = _load_active_tracking_for_user(db, analysis_id, user_id)
        category = _get_category_row_or_raise(db, tracking.id, category_key)

        current_status = category.status
        _ensure_status_transition(current_status, target_status)

        now = datetime.now(UTC)
        category.status = target_status
        category.updated_by = user_id
        category.updated_at = now
        if target_status == "closed":
            category.closed_by = user_id
            category.closed_at = now
        if current_status == "closed" and target_status == "in_review":
            category.reopened_by = user_id
            category.reopened_at = now

        expected = tracking.updated_at
        new_updated_at = _apply_tracking_cas_update(db, tracking.id, expected, now)
        tracking.updated_at = new_updated_at
        return _to_tracking_payload(db, tracking)
    finally:
        db.close()


def update_tracking_item_status(
    analysis_id: str,
    user_id: str,
    category_key: str,
    tracking_item_id: str,
    target_status: str,
) -> dict:
    from infra.database import SessionLocal
    from tracking.service.serialization import _to_tracking_payload
    from tracking.service.service import _load_active_tracking_for_user

    db = SessionLocal()
    try:
        tracking = _load_active_tracking_for_user(db, analysis_id, user_id)
        category = _get_category_row_or_raise(db, tracking.id, category_key)
        _ensure_category_not_closed(category)

        target = next((item for item in category.items if item.id == tracking_item_id), None)
        if target is None:
            raise ValueError("TRACKING_ITEM_NOT_FOUND")

        now = datetime.now(UTC)
        target.status = target_status
        target.updated_by = user_id
        target.updated_at = now
        category.updated_by = user_id
        category.updated_at = now

        expected = tracking.updated_at
        new_updated_at = _apply_tracking_cas_update(db, tracking.id, expected, now)
        tracking.updated_at = new_updated_at
        return _to_tracking_payload(db, tracking)
    finally:
        db.close()
