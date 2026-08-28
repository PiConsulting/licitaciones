"""Conversion de las filas normalizadas de tracking (Postgres) al payload
publico de la API, con el resumen agregado por categoria calculado en vivo
(nunca cacheado -- mismo criterio que la version Cosmos)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from tracking.models import Tracking
from tracking.service.utils import TRACKING_CATEGORY_KEYS


def _to_tracking_payload(db: Session, tracking: Tracking) -> dict:
    # Import diferido: comments importa de categories, que a su vez importa
    # de este módulo; importar acá arriba crearía un ciclo.
    from tracking.service.comments import _query_comments

    comments = _query_comments(db, tracking.analysis_id)
    comments_by_category: dict[str, int] = {}
    comments_by_item: dict[str, int] = {}
    for comment in comments:
        category_key = comment["category_key"]
        comments_by_category[category_key] = comments_by_category.get(category_key, 0) + 1
        tracking_item_id = comment.get("tracking_item_id")
        if tracking_item_id:
            comments_by_item[tracking_item_id] = comments_by_item.get(tracking_item_id, 0) + 1

    categories_by_key = {category.category_key: category for category in tracking.categories}

    categories: list[dict] = []
    for key in TRACKING_CATEGORY_KEYS:
        category_row = categories_by_key.get(key)
        items: list[dict] = []
        if category_row is not None:
            for item in category_row.items:
                items.append(
                    {
                        "tracking_item_id": item.id,
                        "category_key": key,
                        "source_item_ref": {
                            "version_id": item.source_version_id,
                            "field_name": item.source_field_name,
                            "document_id": item.source_document_id,
                            "page": item.source_page,
                            "citation_hash": item.source_citation_hash,
                        },
                        "status": item.status,
                        "updated_by": item.updated_by,
                        "updated_at": item.updated_at,
                        "comments_count": comments_by_item.get(item.id, 0),
                    }
                )
        categories.append(
            {
                "category_key": key,
                "status": category_row.status if category_row else "not_reviewed",
                "updated_by": category_row.updated_by if category_row else None,
                "updated_at": category_row.updated_at if category_row else None,
                "closed_by": category_row.closed_by if category_row else None,
                "closed_at": category_row.closed_at if category_row else None,
                "reopened_by": category_row.reopened_by if category_row else None,
                "reopened_at": category_row.reopened_at if category_row else None,
                "items": items,
                "comments_count": comments_by_category.get(key, 0),
            }
        )

    return {
        "id": tracking.id,
        "type": "tracking",
        "analysis_id": tracking.analysis_id,
        "version_id": tracking.version_id,
        "status": tracking.status,
        "started_by": tracking.started_by,
        "started_at": tracking.started_at,
        "completed_by": tracking.completed_by,
        "completed_by_name": tracking.completed_by_name,
        "completed_at": tracking.completed_at,
        "updated_at": tracking.updated_at,
        "categories": categories,
        "summary": _build_summary(categories),
    }


def _build_summary(categories: list[dict]) -> dict:
    total = len(TRACKING_CATEGORY_KEYS)
    not_reviewed = sum(1 for category in categories if category.get("status") == "not_reviewed")
    in_review = sum(1 for category in categories if category.get("status") == "in_review")
    closed = sum(1 for category in categories if category.get("status") == "closed")
    percentage = round((closed / total) * 100) if total else 0
    return {
        "total_categories": total,
        "not_reviewed": not_reviewed,
        "in_review": in_review,
        "closed": closed,
        "closed_percentage": percentage,
    }
