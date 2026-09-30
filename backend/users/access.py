from __future__ import annotations

from sqlalchemy import ColumnElement, false, true
from sqlalchemy.orm import Session

from analysis.models import Analysis
from infra.business_units import BUSINESS_UNITS
from users.models import User
from users.roles import UserRole


def is_superadmin(user: User) -> bool:
    return user.role == UserRole.SUPERADMIN.value


def analysis_scope_for_user(user: User) -> ColumnElement[bool]:
    if is_superadmin(user):
        return true()
    if not user.business_unit:
        return false()
    return Analysis.business_unit == user.business_unit


def analysis_scope_filter(db: Session, user_id: str) -> ColumnElement[bool]:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return false()
    return analysis_scope_for_user(user)


def get_visible_analysis(db: Session, analysis_id: str, user_id: str) -> Analysis | None:
    return (
        db.query(Analysis)
        .filter(
            Analysis.id == analysis_id,
            Analysis.deleted_at.is_(None),
            analysis_scope_filter(db, user_id),
        )
        .first()
    )


def visible_business_units(db: Session, user_id: str) -> tuple[str, ...]:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return ()
    if is_superadmin(user):
        return BUSINESS_UNITS
    return tuple(unit for unit in BUSINESS_UNITS if unit == user.business_unit)
