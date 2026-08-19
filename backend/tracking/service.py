from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosAccessConditionFailedError, CosmosResourceNotFoundError

from analysis import cosmos_runtime

TRACKING_CATEGORY_KEYS = [
    "objeto_alcance",
    "requisitos_admisibilidad",
    "garantias",
    "plazos_clave",
    "criterios_evaluacion",
    "causales_rechazo",
    "anexos_obligatorios",
]

ACTIONABLE_CHECKLIST_CATEGORIES = {"requisitos_admisibilidad", "anexos_obligatorios"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _tracking_id(analysis_id: str, version_id: str) -> str:
    return f"tracking::{analysis_id}::{version_id}"


def _load_analysis_or_raise(analysis_id: str, user_id: str) -> dict:
    container = cosmos_runtime.get_cosmos_container()
    item_id = f"analysis::{analysis_id}"
    analysis = None
    for pk in [analysis_id, item_id]:
        try:
            analysis = container.read_item(item=item_id, partition_key=pk)
            break
        except Exception:  # noqa: BLE001
            continue
    if analysis is None or analysis.get("deleted"):
        rows = list(
            container.query_items(
                query="SELECT TOP 1 * FROM c WHERE c.type = 'analysis' AND c.analysis_id = @analysis_id",
                parameters=[{"name": "@analysis_id", "value": analysis_id}],
                enable_cross_partition_query=True,
            )
        )
        if rows:
            analysis = rows[0]
    if analysis is None or analysis.get("deleted"):
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")
    return analysis


def _load_latest_version(analysis_id: str) -> dict:
    container = cosmos_runtime.get_cosmos_container()
    rows = list(
        container.query_items(
            query=(
                "SELECT TOP 1 * FROM c WHERE c.type = 'analysis_version' "
                "AND c.analysis_id = @analysis_id ORDER BY c.version_number DESC"
            ),
            parameters=[{"name": "@analysis_id", "value": analysis_id}],
            partition_key=analysis_id,
        )
    )
    if not rows:
        raise ValueError("NO_VERSION_YET")
    return rows[0]


def _read_tracking_or_none(analysis_id: str, version_id: str) -> dict | None:
    container = cosmos_runtime.get_cosmos_container()
    item_id = _tracking_id(analysis_id, version_id)
    try:
        return container.read_item(item=item_id, partition_key=analysis_id)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        return None


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


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


def _extract_tracking_items_from_version(*, version_id: str, category_key: str, extracted_data: dict) -> list[dict]:
    raw_items = extracted_data.get(category_key)
    if not isinstance(raw_items, list):
        return []
    items: list[dict] = []
    for idx, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        refs = raw_item.get("source_references") if isinstance(raw_item.get("source_references"), list) else []
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
                    "citation_hash": sha256(citation_text.encode("utf-8")).hexdigest()[:16] if citation_text else None,
                },
                "status": "not_evaluated",
                "updated_by": None,
                "updated_at": None,
            }
        )
    return items


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


def _save_tracking_with_etag(tracking: dict) -> None:
    container = cosmos_runtime.get_cosmos_container()
    etag = tracking.get("_etag")
    if etag:
        result = container.replace_item(
            item=tracking["id"],
            body=tracking,
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
        )
    else:
        result = container.upsert_item(tracking)
    if isinstance(result, dict) and result.get("_etag"):
        tracking["_etag"] = result["_etag"]


def _ensure_status_transition(current: str, target: str) -> None:
    allowed = {
        "not_reviewed": {"in_review", "closed"},
        "in_review": {"closed"},
        "closed": {"in_review"},
    }
    if target not in allowed.get(current, set()):
        raise ValueError("INVALID_TRACKING_TRANSITION")


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


def _build_summary(categories: list[dict]) -> dict:
    total = len(TRACKING_CATEGORY_KEYS)
    not_reviewed = sum(1 for category in categories if category.get("status") == "not_reviewed")
    in_review = sum(1 for category in categories if category.get("status") == "in_review")
    closed = sum(1 for category in categories if category.get("status") == "closed")
    percentage = int(round((closed / total) * 100)) if total else 0
    return {
        "total_categories": total,
        "not_reviewed": not_reviewed,
        "in_review": in_review,
        "closed": closed,
        "closed_percentage": percentage,
    }


def _to_tracking_payload(tracking: dict) -> dict:
    comments = _query_comments(str(tracking.get("analysis_id")))
    comments_by_category: dict[str, int] = {}
    comments_by_item: dict[str, int] = {}
    for comment in comments:
        category_key = str(comment.get("category_key") or "")
        comments_by_category[category_key] = comments_by_category.get(category_key, 0) + 1
        tracking_item_id = comment.get("tracking_item_id")
        if tracking_item_id:
            key = str(tracking_item_id)
            comments_by_item[key] = comments_by_item.get(key, 0) + 1

    categories: list[dict] = []
    raw_categories = tracking.get("categories") if isinstance(tracking.get("categories"), dict) else {}
    for key in TRACKING_CATEGORY_KEYS:
        raw = raw_categories.get(key) if isinstance(raw_categories.get(key), dict) else {}
        items: list[dict] = []
        for item in raw.get("items") if isinstance(raw.get("items"), list) else []:
            if not isinstance(item, dict):
                continue
            mapped = dict(item)
            mapped["updated_at"] = _parse_dt(item.get("updated_at"))
            mapped["comments_count"] = comments_by_item.get(str(item.get("tracking_item_id")), 0)
            items.append(mapped)
        categories.append(
            {
                "category_key": key,
                "status": raw.get("status", "not_reviewed"),
                "updated_by": raw.get("updated_by"),
                "updated_at": _parse_dt(raw.get("updated_at")),
                "closed_by": raw.get("closed_by"),
                "closed_at": _parse_dt(raw.get("closed_at")),
                "reopened_by": raw.get("reopened_by"),
                "reopened_at": _parse_dt(raw.get("reopened_at")),
                "items": items,
                "comments_count": comments_by_category.get(key, 0),
            }
        )

    return {
        "id": tracking.get("id"),
        "type": "tracking",
        "analysis_id": tracking.get("analysis_id"),
        "version_id": tracking.get("version_id"),
        "status": tracking.get("status", "active"),
        "started_by": tracking.get("started_by"),
        "started_at": _parse_dt(tracking.get("started_at")),
        "completed_by": tracking.get("completed_by"),
        "completed_by_name": tracking.get("completed_by_name"),
        "completed_at": _parse_dt(tracking.get("completed_at")),
        "updated_at": _parse_dt(tracking.get("updated_at")),
        "categories": categories,
        "summary": _build_summary(categories),
    }


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
        "created_by_name": created_by_name if created_by_name is not None else str(row.get("created_by_name") or ""),
        "created_at": _parse_dt(row.get("created_at")),
        "edited_by": row.get("edited_by"),
        "edited_by_name": row.get("edited_by_name"),
        "edited_at": _parse_dt(row.get("edited_at")),
        "deleted": bool(row.get("deleted", False)),
        "deleted_at": _parse_dt(row.get("deleted_at")),
        "deleted_by": row.get("deleted_by"),
    }


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
        "categories": _build_default_categories(version_id=version_id, extracted_data=version.get("extracted_data") or {}),
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


def update_category_status(analysis_id: str, user_id: str, category_key: str, target_status: str) -> dict:
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
    category = categories.get(category_key) if isinstance(categories.get(category_key), dict) else None
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
            "event": "category_reopened" if (current_status == "closed" and target_status == "in_review") else "category_status_changed",
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


def _get_comment_or_raise(analysis_id: str, comment_id: str, *, category_key: str | None = None) -> dict:
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


def update_tracking_item_status(
    analysis_id: str,
    user_id: str,
    category_key: str,
    tracking_item_id: str,
    target_status: str,
) -> dict:
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


def list_comments(
    analysis_id: str,
    user_id: str,
    category_key: str,
    *,
    scope: str | None = None,
    tracking_item_id: str | None = None,
) -> list[dict]:
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


def complete_tracking(analysis_id: str, user_id: str, *, completed_by_name: str | None = None) -> dict:
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
    raw["completed_by_name"] = (completed_by_name or "").strip() or _resolve_user_display_name(user_id)
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


def update_comment(
    analysis_id: str,
    user_id: str,
    category_key: str,
    comment_id: str,
    *,
    content: str,
    edited_by_name: str | None = None,
) -> dict:
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
    comment["edited_by_name"] = (edited_by_name or "").strip() or _resolve_user_display_name(user_id)
    comment["edited_at"] = now

    cosmos_runtime.get_cosmos_container().upsert_item(comment)
    return _serialize_comment(comment)


def delete_comment(analysis_id: str, user_id: str, category_key: str, comment_id: str) -> None:
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
