"""Conversion del documento interno de tracking (Cosmos) al payload publico de la API, con el resumen agregado por categoria."""
from __future__ import annotations

from tracking.service.utils import TRACKING_CATEGORY_KEYS, _parse_dt


def _to_tracking_payload(tracking: dict) -> dict:
    # Import diferido: comments importa de categories, que a su vez importa
    # de este módulo (_to_tracking_payload); importar acá arriba crearía un
    # ciclo. Sólo esta función necesita _query_comments.
    from tracking.service.comments import _query_comments

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
    raw_categories = (
        tracking.get("categories") if isinstance(tracking.get("categories"), dict) else {}
    )
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
