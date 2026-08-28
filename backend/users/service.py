from datetime import UTC, datetime, timedelta
from typing import NoReturn

import jwt
import structlog
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from infra.config import get_settings
from infra.database import SessionLocal
from users.models import User

logger = structlog.get_logger(__name__)

http_bearer = HTTPBearer(auto_error=False)


def _raise_auth_backend_unavailable(exc: Exception) -> NoReturn:
    # Mismo criterio que tenía el camino Cosmos (auditoría 2026-08-12):
    # un fallo de conexión al backend de auth no es lo mismo que "no hay
    # usuario" -- acá sería tratar cualquier sesión válida como inválida
    # (401 falso) durante un outage de Postgres. Se distingue y se propaga
    # como 503 para que quede claro que el problema es de disponibilidad,
    # no de la sesión del usuario.
    logger.warning("auth_backend_connection_failed", error=str(exc)[:200])
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": {
                "code": "AUTH_BACKEND_UNAVAILABLE",
                "message": "Servicio de autenticación no disponible",
            }
        },
    ) from exc


def get_password_hash(password: str) -> str:
    return bcrypt.using(rounds=12).hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.verify(plain_password, password_hash)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.jwt_expiration_hours)
    payload = {
        "user_id": user_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def authenticate_user(db: Session | None, email: str, password: str) -> User | None:
    managed_db = db or SessionLocal()
    try:
        stmt: Select[tuple[User]] = select(User).where(
            User.email == email, User.deleted_at.is_(None)
        )
        try:
            user = managed_db.execute(stmt).scalar_one_or_none()
        except OperationalError as exc:
            _raise_auth_backend_unavailable(exc)
    finally:
        if db is None:
            managed_db.close()

    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def decode_and_validate_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None, db: Session | None
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "MISSING_AUTH", "message": "No autorizado"}},
        )

    payload = decode_and_validate_token(credentials.credentials)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        )

    managed_db = db or SessionLocal()
    try:
        try:
            user = managed_db.get(User, user_id)
        except OperationalError as exc:
            _raise_auth_backend_unavailable(exc)
    finally:
        if db is None:
            managed_db.close()

    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        )

    return user


def register_user(db: Session | None, name: str, email: str, password: str) -> User:
    normalized_name = name.strip()
    normalized_email = email.strip().lower()

    user = User(
        name=normalized_name,
        email=normalized_email,
        password_hash=get_password_hash(password),
    )

    managed_db = db or SessionLocal()
    try:
        managed_db.add(user)
        managed_db.commit()
        managed_db.refresh(user)
        return user
    except IntegrityError as exc:
        managed_db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "EMAIL_ALREADY_EXISTS",
                    "message": "Este email ya está registrado",
                }
            },
        ) from exc
    except OperationalError as exc:
        managed_db.rollback()
        _raise_auth_backend_unavailable(exc)
    finally:
        if db is None:
            managed_db.close()
