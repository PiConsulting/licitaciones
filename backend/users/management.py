from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infra.business_units import business_unit_for_email_domain
from infra.config import get_settings
from users.models import User
from users.roles import UserRole
from users.schemas import UserCreateRequest, UserUpdateRequest
from users.service import get_password_hash, raise_user_suspended
from users.sso import DomainNotMappedError, SsoClaims


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _email_taken() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "EMAIL_ALREADY_EXISTS", "Este email ya está registrado")


def list_users(db: Session) -> list[User]:
    stmt = select(User).where(User.deleted_at.is_(None)).order_by(User.name, User.email)
    return list(db.execute(stmt).scalars())


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "Usuario no encontrado")
    return user


def _email_in_use(db: Session, email: str, exclude_id: str | None = None) -> bool:
    stmt = select(User.id).where(User.email == email)
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return db.execute(stmt).first() is not None


def create_user(db: Session, payload: UserCreateRequest) -> User:
    if _email_in_use(db, payload.email):
        raise _email_taken()

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        role=payload.role.value,
        business_unit=payload.business_unit,
        is_active=payload.is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _email_taken() from exc
    db.refresh(user)
    return user


def update_user(
    db: Session, actor: User, user_id: str, payload: UserUpdateRequest
) -> User:
    user = _get_user_or_404(db, user_id)
    is_self = user.id == actor.id

    if is_self and payload.role is not None and payload.role != UserRole.SUPERADMIN:
        raise _error(
            status.HTTP_409_CONFLICT,
            "SELF_ROLE_CHANGE_FORBIDDEN",
            "No podés quitarte el rol de superadmin",
        )
    if is_self and payload.is_active is False:
        raise _error(
            status.HTTP_409_CONFLICT,
            "SELF_SUSPEND_FORBIDDEN",
            "No podés suspender tu propio usuario",
        )

    if payload.email is not None and payload.email != user.email:
        if _email_in_use(db, payload.email, exclude_id=user.id):
            raise _email_taken()
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    if payload.business_unit is not None:
        user.business_unit = payload.business_unit
    if payload.role is not None:
        user.role = payload.role.value
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = get_password_hash(payload.password)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _email_taken() from exc
    db.refresh(user)
    return user


def get_or_create_sso_user(db: Session, claims: SsoClaims) -> User:
    """JIT provisioning (Historia 25.2): crea o reutiliza el usuario autenticado por SSO.

    Las excepciones de rol (`SSO_SUPERADMIN_EMAILS`) solo afectan `role`, nunca `business_unit`.
    """
    email = claims.email.strip().lower()
    is_exception = email in get_settings().superadmin_emails_set()
    resolved_business_unit = business_unit_for_email_domain(email)

    if resolved_business_unit is None and not is_exception:
        raise DomainNotMappedError(email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None:
        user = User(
            name=claims.name,
            email=email,
            # Password no utilizable: este usuario solo puede entrar vía SSO.
            password_hash=get_password_hash(secrets.token_urlsafe(32)),
            role=(UserRole.SUPERADMIN if is_exception else UserRole.MIEMBRO).value,
            business_unit=resolved_business_unit,
        )
        db.add(user)
    else:
        if user.deleted_at is not None:
            raise _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "Usuario no encontrado")
        if not user.is_active:
            raise_user_suspended(status.HTTP_403_FORBIDDEN)
        if is_exception and user.role != UserRole.SUPERADMIN.value:
            user.role = UserRole.SUPERADMIN.value
        user.last_login_at = datetime.now(UTC)

    db.commit()
    db.refresh(user)
    return user
