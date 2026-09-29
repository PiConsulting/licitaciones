"""Listado paginado de analisis del usuario con filtros y busqueda."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sqlalchemy import String, and_, asc, cast, desc, func, or_
from sqlalchemy.orm import Session

from analysis.models import Analysis, AnalysisVersion, BusinessStatus
from analysis.utils import calculate_confidence_avg
from documents.models import Document


BUSINESS_UNIT_CATALOG: tuple[str, ...] = ("CEDI", "PI", "Wemox", "Vulps", "Korex")


def list_analyses(
    db: Session,
    *,
    user_id: str,
    search: str | None = None,
    status_filter: str | None = None,
    business_unit_filter: str | None = None,
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

    if business_unit_filter and business_unit_filter.strip():
        query = query.filter(Analysis.business_unit == business_unit_filter.strip())

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

        monto_estimado, moneda = _extract_estimated_amount(extracted_data)

        items.append(
            {
                "id": analysis.id,
                "analysis_name": analysis.analysis_name,
                "business_unit": analysis.business_unit,
                "status": analysis.status,
                "business_status": analysis.business_status,
                "current_stage": analysis.current_stage,
                "stage_progress": stage_progress,
                "progress_percentage": analysis.progress_percentage or 0,
                "confidence_avg": calculate_confidence_avg(extracted_data),
                "created_at": analysis.created_at,
                "primary_document_name": primary_document_name,
                "organismo": _extract_organism(extracted_data),
                "created_by_name": created_by_name,
                "monto_estimado": monto_estimado,
                "moneda": moneda,
            }
        )

    return items, total


def list_business_units(
    db: Session,
    *,
    user_id: str,
    search: str | None = None,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    primary_document = Document

    query = (
        db.query(
            Analysis.business_unit.label("business_unit"),
            func.count(Analysis.id).label("count"),
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
        .filter(
            Analysis.created_by == user_id,
            Analysis.deleted_at.is_(None),
            Analysis.business_unit.is_not(None),
            Analysis.business_unit != "",
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

    rows = (
        query.group_by(Analysis.business_unit)
        .order_by(asc(Analysis.business_unit))
        .all()
    )

    counts: dict[str, int] = {
        row.business_unit.strip(): int(row.count)
        for row in rows
        if isinstance(row.business_unit, str) and row.business_unit.strip()
    }

    units: list[dict] = [
        {
            "business_unit": business_unit,
            "count": counts.get(business_unit, 0),
        }
        for business_unit in BUSINESS_UNIT_CATALOG
    ]

    # Mantener compatibilidad con unidades históricas fuera del catálogo oficial.
    extra_units = sorted(unit for unit in counts if unit not in BUSINESS_UNIT_CATALOG)
    units.extend(
        {
            "business_unit": unit,
            "count": counts[unit],
        }
        for unit in extra_units
    )

    return units


def get_business_status_summary(
    db: Session,
    *,
    user_id: str,
    business_unit: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Conteo de analisis por `business_status` (Story FE5.4). `total` cuenta todos los
    analisis que matchean los filtros, incluidos los que todavia no tienen `business_status`
    asignado; `by_status` solo cubre los 7 valores conocidos de `BusinessStatus`."""
    query = db.query(
        Analysis.business_status.label("business_status"),
        func.count(Analysis.id).label("count"),
    ).filter(
        Analysis.created_by == user_id,
        Analysis.deleted_at.is_(None),
    )

    if business_unit and business_unit.strip():
        query = query.filter(Analysis.business_unit == business_unit.strip())

    if date_from:
        date_from_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at >= date_from_dt)

    if date_to:
        date_to_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
        query = query.filter(Analysis.created_at <= date_to_dt)

    rows = query.group_by(Analysis.business_status).all()

    raw_counts: dict[str, int] = {
        row.business_status: int(row.count) for row in rows if row.business_status is not None
    }
    total = sum(int(row.count) for row in rows)

    by_status = {value.value: raw_counts.get(value.value, 0) for value in BusinessStatus}

    return {"total": total, "by_status": by_status}


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


# Reconoce U$S/USD/US$ antes que "$" a secas -- si no, "U$S 19.800" matchearía
# primero el "$" suelto y perdería la moneda real. Sin match, default ARS (mismo
# criterio que ya usa `AnalysisTable.tsx::formatEstimatedAmount` en el frontend).
_USD_RE = re.compile(r"u\$s|us\$|usd|d[oó]lares?", re.IGNORECASE)
# Monto en notación argentina ("." miles + "," decimal, ej. "19.800,00") O con
# punto decimal sin miles (ej. "654484.26", "40.50" -- visto en extracciones
# reales). BUG real: la versión anterior solo reconocía "," como decimal: un
# monto con punto decimal como "654484.26" matcheaba solo "654484" y los
# centavos (".26") quedaban afuera del match, no solo mal redondeados.
# Orden importa: el primer alternativo (miles) debe probarse antes que el de
# "punto decimal sin miles", si no "19.800,00" perdería el agrupamiento.
_AMOUNT_RE = re.compile(
    r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?"  # 19.800,00 / 15 000 000
    r"|\d+,\d+"  # 19800,00 (decimal con coma, sin miles)
    r"|\d+\.\d{1,2}(?!\d)"  # 654484.26 (decimal con punto, 1-2 dígitos -- nunca es agrupamiento de miles)
    r"|\d+"  # 19800 (entero sin separadores)
)


def _parse_estimated_amount(text: str) -> tuple[float | None, str | None]:
    """Parsea el texto libre de "Presupuesto oficial" (ej. "U$S 19.800,00",
    "USD654.484,26 IVA Incluido") a (monto, moneda). Nunca inventa un monto: si
    no hay una cifra reconocible (ej. "$ X" como placeholder del pliego),
    devuelve (None, moneda detectada o None) en vez de forzar un número."""
    currency = "USD" if _USD_RE.search(text) else ("ARS" if "$" in text else None)

    match = _AMOUNT_RE.search(text)
    if not match:
        return None, currency

    raw = match.group(0).replace(" ", "")
    if "," in raw:
        # Notación argentina: "." (si hay) es miles, "," es el decimal.
        normalized = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+\.\d{1,2}", raw):
        # Punto decimal sin miles (ej. "654484.26") -- se deja tal cual, NUNCA se le saca el punto.
        normalized = raw
    else:
        # Puntos de miles sin decimal (ej. "15.000.000"), o entero sin separadores.
        normalized = raw.replace(".", "")

    try:
        amount = float(normalized)
    except ValueError:
        return None, currency

    return amount, (currency or "ARS")


def _extract_estimated_amount(extracted_data: dict | None) -> tuple[float | None, str | None]:
    if not isinstance(extracted_data, dict):
        return None, None

    datos_procedimiento = extracted_data.get("datos_procedimiento")
    items = datos_procedimiento if isinstance(datos_procedimiento, list) else None
    if items is None and isinstance(datos_procedimiento, dict):
        candidate = datos_procedimiento.get("items")
        items = candidate if isinstance(candidate, list) else None

    if not items:
        return None, None

    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("tipo") or item.get("field_name") or "").lower()
        if "presupuesto" not in label:
            continue
        value = item.get("valor") if "valor" in item else item.get("field_value")
        if isinstance(value, str) and value.strip():
            return _parse_estimated_amount(value.strip())

    return None, None
