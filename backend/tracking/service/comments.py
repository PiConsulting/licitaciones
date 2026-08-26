"""Comentarios de tracking: alta, edicion (soft), borrado (soft) y listado con nombre de autor resuelto."""
from __future__ import annotations

from uuid import uuid4

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from analysis import cosmos_runtime
from tracking.service.categories import (
    _ensure_category_not_closed,
    _get_category_or_raise,
    ensure_tracking_active_or_raise,
)
from tracking.service.storage import _read_tracking_or_none
from tracking.service.utils import _now_iso, _parse_dt


def _query_comments(analysis_id: str, category_key: str | None = None) -> list[dict]:
    container = cosmos_runtime.get_cosmos_container()
    query = (
        "SELECT * FROM c WHERE c.type = 'tracking_comment' AND c.analysis_id = @analysis_id "
        "AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
    )
    parameters = [{"name": "@analysis_id", "value": analysis_id}]
    if category_key is not None:
        query += " AND c.category_key = @category_key"
        parameters.append({"name": "@category_key", "value": category_key})
    rows = list(
        container.query_items(
            query=query,
            parameters=parameters,
            partition_key=analysis_id,
        )
    )
    rows.sort(key=lambda item: str(item.get("created_at") or ""))
    return rows


def _resolve_user_display_name(user_id: str) -> str:
    if not user_id:
        return "Usuario desconocido"
    container = cosmos_runtime.get_cosmos_container()
    try:
        user = container.read_item(item=f"user::{user_id}", partition_key=f"user::{user_id}")
    except Exception:  # noqa: BLE001
        return user_id
    name = str(user.get("name") or "").strip()
    email = str(user.get("email") or "").strip()
    return name or email or user_id


def list_comments(
    analysis_id: str,
    user_id: str,
    category_key: str,
    *,
    scope: str | None = None,
    tracking_item_id: str | None = None,
) -> list[dict]:
    # Import diferido: service importa _resolve_user_display_name de este
    # módulo; importar get_tracking acá arriba crearía un ciclo.
    from tracking.service.service import get_tracking

    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")
    rows = _query_comments(analysis_id, category_key=category_key)
    display_names: dict[str, str] = {}
    result = []
    for row in rows:
        if scope and row.get("scope") != scope:
            continue
        if tracking_item_id and row.get("tracking_item_id") != tracking_item_id:
            continue
        created_by = str(row.get("created_by") or "")
        created_by_name = str(row.get("created_by_name") or "").strip()
        if not created_by_name:
            if created_by not in display_names:
                display_names[created_by] = _resolve_user_display_name(created_by)
            created_by_name = display_names[created_by]
        result.append(_serialize_comment(row, created_by_name=created_by_name))
    return result


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

    if scope != "category" or tracking_item_id:
        raise ValueError("TRACKING_CATEGORY_COMMENT_ONLY")

    now = _now_iso()
    comment_id = f"tracking_comment::{uuid4()}"
    item = {
        "id": comment_id,
        "type": "tracking_comment",
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "version_id": tracking["version_id"],
        "category_key": category_key,
        "scope": "category",
        "tracking_item_id": None,
        "content": content.strip(),
        "created_by": user_id,
        "created_by_name": (created_by_name or "").strip() or _resolve_user_display_name(user_id),
        "created_at": now,
        "deleted": False,
    }
    cosmos_runtime.get_cosmos_container().upsert_item(item)

    return _serialize_comment(item)


def _get_comment_or_raise(
    analysis_id: str, comment_id: str, *, category_key: str | None = None
) -> dict:
    container = cosmos_runtime.get_cosmos_container()
    try:
        comment = container.read_item(item=comment_id, partition_key=analysis_id)
    except CosmosResourceNotFoundError as exc:
        raise ValueError("TRACKING_COMMENT_NOT_FOUND") from exc
    if comment.get("type") != "tracking_comment" or comment.get("analysis_id") != analysis_id:
        raise ValueError("TRACKING_COMMENT_NOT_FOUND")
    if category_key and comment.get("category_key") != category_key:
        raise ValueError("TRACKING_COMMENT_NOT_FOUND")
    if comment.get("deleted"):
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
    from tracking.service.service import get_tracking

    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    raw = _read_tracking_or_none(analysis_id, str(tracking["version_id"]))
    if raw is None:
        raise ValueError("TRACKING_NOT_FOUND")
    ensure_tracking_active_or_raise(raw)

    comment = _get_comment_or_raise(analysis_id, comment_id, category_key=category_key)
    now = _now_iso()
    comment["content"] = content.strip()
    comment["edited_by"] = user_id
    comment["edited_by_name"] = (edited_by_name or "").strip() or _resolve_user_display_name(
        user_id
    )
    comment["edited_at"] = now

    cosmos_runtime.get_cosmos_container().upsert_item(comment)
    return _serialize_comment(comment)


def delete_comment(analysis_id: str, user_id: str, category_key: str, comment_id: str) -> None:
    from tracking.service.service import get_tracking

    tracking = get_tracking(analysis_id, user_id)
    if tracking is None:
        raise ValueError("TRACKING_NOT_FOUND")

    raw = _read_tracking_or_none(analysis_id, str(tracking["version_id"]))
    if raw is None:
        raise ValueError("TRACKING_NOT_FOUND")
    ensure_tracking_active_or_raise(raw)

    comment = _get_comment_or_raise(analysis_id, comment_id, category_key=category_key)
    comment["deleted"] = True
    comment["deleted_at"] = _now_iso()
    comment["deleted_by"] = user_id
    cosmos_runtime.get_cosmos_container().upsert_item(comment)


def _serialize_comment(row: dict, *, created_by_name: str | None = None) -> dict:
    return {
        "id": str(row.get("id")),
        "analysis_id": str(row.get("analysis_id")),
        "version_id": str(row.get("version_id")),
        "category_key": str(row.get("category_key")),
        "scope": "category",
        "tracking_item_id": None,
        "content": str(row.get("content") or ""),
        "created_by": str(row.get("created_by") or ""),
        "created_by_name": created_by_name
        if created_by_name is not None
        else str(row.get("created_by_name") or ""),
        "created_at": _parse_dt(row.get("created_at")),
        "edited_by": row.get("edited_by"),
        "edited_by_name": row.get("edited_by_name"),
        "edited_at": _parse_dt(row.get("edited_at")),
        "deleted": bool(row.get("deleted", False)),
        "deleted_at": _parse_dt(row.get("deleted_at")),
        "deleted_by": row.get("deleted_by"),
    }
