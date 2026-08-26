"""Listado paginado de analisis del usuario con filtros y busqueda."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import String, and_, asc, cast, desc, func, or_
from sqlalchemy.orm import Session

from analysis.models import Analysis, AnalysisVersion
from analysis.utils import calculate_confidence_avg
from documents.models import Document


def list_analyses(
    db: Session,
    *,
    user_id: str,
    search: str | None = None,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    primary_document = Document
    sort_columns = {
        "created_at": Analysis.created_at,
        "status": Analysis.status,
        "current_stage": Analysis.current_stage,
    }
    selected_sort = sort_columns.get(sort_by, Analysis.created_at)
    selected_order = asc if sort_order == "asc" else desc

    from users.models import User

    query = (
        db.query(
            Analysis,
            primary_document.filename.label("primary_document_name"),
            AnalysisVersion.extracted_data.label("extracted_data"),
            User.name.label("created_by_name"),
        )
        .outerjoin(
            primary_document,
            and_(
                primary_document.analysis_id == Analysis.id,
                primary_document.is_primary.is_(True),
                primary_document.deleted_at.is_(None),
            ),
        )
        .outerjoin(AnalysisVersion, AnalysisVersion.id == Analysis.current_version_id)
        .outerjoin(User, User.id == Analysis.created_by)
        .filter(
            Analysis.created_by == user_id,
            Analysis.deleted_at.is_(None),
        )
    )

    if status_filter:
        query = query.filter(Analysis.status == status_filter)

    if date_from:
        date_from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at >= date_from_dt)

    if date_to:
        date_to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at <= date_to_dt)

    if search and search.strip():
        normalized = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(func.coalesce(Analysis.analysis_name, "")).like(normalized),
                func.lower(func.coalesce(primary_document.filename, "")).like(normalized),
                func.lower(func.coalesce(cast(AnalysisVersion.extracted_data, String), "")).like(
                    normalized
                ),
                func.lower(func.coalesce(Analysis.id, "")).like(normalized),
            )
        )

    total = query.count()
    rows = (
        query.order_by(selected_order(selected_sort), desc(Analysis.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items: list[dict] = []
    for analysis, primary_document_name, extracted_data, created_by_name in rows:
        stage_progress = None
        if isinstance(analysis.extraction_metadata, dict):
            raw_progress = analysis.extraction_metadata.get("stage_progress")
            if isinstance(raw_progress, str):
                stage_progress = raw_progress

        items.append(
            {
                "id": analysis.id,
                "analysis_name": analysis.analysis_name,
                "status": analysis.status,
                "current_stage": analysis.current_stage,
                "stage_progress": stage_progress,
                "progress_percentage": analysis.progress_percentage or 0,
                "confidence_avg": calculate_confidence_avg(extracted_data),
                "created_at": analysis.created_at,
                "primary_document_name": primary_document_name,
                "organismo": _extract_organism(extracted_data),
                "created_by_name": created_by_name,
            }
        )

    return items, total


def _extract_organism(extracted_data: dict | None) -> str | None:
    if not isinstance(extracted_data, dict):
        return None

    datos_procedimiento = extracted_data.get("datos_procedimiento")
    items = datos_procedimiento if isinstance(datos_procedimiento, list) else None
    if items is None and isinstance(datos_procedimiento, dict):
        candidate = datos_procedimiento.get("items")
        items = candidate if isinstance(candidate, list) else None

    if items:
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("tipo") or item.get("field_name") or "").lower()
            if "organismo" not in label:
                continue
            value = item.get("valor") if "valor" in item else item.get("field_value")
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key, value in extracted_data.items():
        if "organismo" not in str(key).lower():
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None
