"""Comentarios de tracking: alta, edicion (soft), borrado (soft) y listado
con nombre de autor resuelto."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from tracking.models import TrackingComment
from tracking.service.categories import _ensure_category_not_closed, _get_category_row_or_raise
from users.models import User


def _row_to_dict(row: TrackingComment) -> dict:
    return {
        "id": row.id,
        "analysis_id": row.analysis_id,
        "version_id": row.version_id,
        "category_key": row.category_key,
        "scope": row.scope,
        "tracking_item_id": row.tracking_item_id,
        "content": row.content,
        "created_by": row.created_by,
        "created_by_name": row.created_by_name,
        "created_at": row.created_at,
        "edited_by": row.edited_by,
        "edited_by_name": row.edited_by_name,
        "edited_at": row.edited_at,
        "deleted": row.deleted,
        "deleted_at": row.deleted_at,
        "deleted_by": row.deleted_by,
    }


def _query_comments(db: Session, analysis_id: str, category_key: str | None = None) -> list[dict]:
    query = db.query(TrackingComment).filter(
        TrackingComment.analysis_id == analysis_id, TrackingComment.deleted.is_(False)
    )
    if category_key is not None:
        query = query.filter(TrackingComment.category_key == category_key)
    rows = query.order_by(TrackingComment.created_at.asc()).all()
    return [_row_to_dict(row) for row in rows]


def _resolve_user_display_name(db: Session, user_id: str) -> str:
    if not user_id:
        return "Usuario desconocido"
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return user_id
    name = (user.name or "").strip()
    email = (user.email or "").strip()
    return name or email or user_id


def list_comments(
    analysis_id: str,
    user_id: str,
    category_key: str,
    *,
    scope: str | None = None,
    tracking_item_id: str | None = None,
) -> list[dict]:
    from infra.database import SessionLocal
    from tracking.service.service import get_tracking

    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    db = SessionLocal()
    try:
        rows = _query_comments(db, analysis_id, category_key=category_key)
        display_names: dict[str, str] = {}
        result = []
        for row in rows:
            if scope and row["scope"] != scope:
                continue
            if tracking_item_id and row["tracking_item_id"] != tracking_item_id:
                continue
            created_by = row["created_by"] or ""
            created_by_name = (row["created_by_name"] or "").strip()
            if not created_by_name:
                if created_by not in display_names:
                    display_names[created_by] = _resolve_user_display_name(db, created_by)
                created_by_name = display_names[created_by]
            result.append({**row, "created_by_name": created_by_name})
        return result
    finally:
        db.close()


def create_comment(
    analysis_id: str,
    user_id: str,
    category_key: str,
    *,
    scope: str,
    content: str,
    tracking_item_id: str | None,
    created_by_name: str | None = None,
) -> dict:
    from infra.database import SessionLocal
    from tracking.service.service import _load_active_tracking_for_user

    if scope != "category" or tracking_item_id:
        raise ValueError("TRACKING_CATEGORY_COMMENT_ONLY")

    db = SessionLocal()
    try:
        tracking = _load_active_tracking_for_user(db, analysis_id, user_id)
        category = _get_category_row_or_raise(db, tracking.id, category_key)
        _ensure_category_not_closed(category)

        row = TrackingComment(
            analysis_id=analysis_id,
            version_id=tracking.version_id,
            category_key=category_key,
            scope="category",
            tracking_item_id=None,
            content=content.strip(),
            created_by=user_id,
            created_by_name=(created_by_name or "").strip()
            or _resolve_user_display_name(db, user_id),
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)
    finally:
        db.close()


def _get_comment_or_raise(
    db: Session, analysis_id: str, comment_id: str, *, category_key: str | None = None
) -> TrackingComment:
    comment = (
        db.query(TrackingComment)
        .filter(TrackingComment.id == comment_id, TrackingComment.analysis_id == analysis_id)
        .first()
    )
    if comment is None or comment.deleted:
        raise ValueError("TRACKING_COMMENT_NOT_FOUND")
    if category_key and comment.category_key != category_key:
        raise ValueError("TRACKING_COMMENT_NOT_FOUND")
    return comment


def update_comment(
    analysis_id: str,
    user_id: str,
    category_key: str,
    comment_id: str,
    *,
    content: str,
    edited_by_name: str | None = None,
) -> dict:
    from infra.database import SessionLocal
    from tracking.service.service import _load_active_tracking_for_user

    db = SessionLocal()
    try:
        _load_active_tracking_for_user(db, analysis_id, user_id)
        comment = _get_comment_or_raise(db, analysis_id, comment_id, category_key=category_key)

        comment.content = content.strip()
        comment.edited_by = user_id
        comment.edited_by_name = (edited_by_name or "").strip() or _resolve_user_display_name(
            db, user_id
        )
        comment.edited_at = datetime.now(UTC)
        db.commit()
        db.refresh(comment)
        return _row_to_dict(comment)
    finally:
        db.close()


def delete_comment(analysis_id: str, user_id: str, category_key: str, comment_id: str) -> None:
    from infra.database import SessionLocal
    from tracking.service.service import _load_active_tracking_for_user

    db = SessionLocal()
    try:
        _load_active_tracking_for_user(db, analysis_id, user_id)
        comment = _get_comment_or_raise(db, analysis_id, comment_id, category_key=category_key)

        comment.deleted = True
        comment.deleted_at = datetime.now(UTC)
        comment.deleted_by = user_id
        db.commit()
    finally:
        db.close()
