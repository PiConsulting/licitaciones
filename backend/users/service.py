from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.cosmos_container import get_cosmos_container
from shared.database import SessionLocal
from users.models import User

http_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    id: str
    email: str
    password_hash: str
    name: str
    deleted_at: datetime | None = None


def _is_cosmos_only_mode() -> bool:
    settings = get_settings()
    return settings.persistence_mode_normalized() == "cosmos_only"


def _build_auth_user_from_item(item: dict) -> AuthUser:
    return AuthUser(
        id=str(item["user_id"]),
        email=str(item["email"]),
        password_hash=str(item["password_hash"]),
        name=str(item.get("name") or ""),
        deleted_at=None,
    )


def _find_user_by_email_cosmos(email: str) -> AuthUser | None:
    container = get_cosmos_container()
    normalized_email = email.strip().lower()
    query = (
        "SELECT TOP 1 * FROM c "
        "WHERE c.type = 'user' AND c.email = @email "
        "AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
    )
    rows = list(
        container.query_items(
            query=query,
            parameters=[{"name": "@email", "value": normalized_email}],
            enable_cross_partition_query=True,
        )
    )
    if not rows:
        return None
    return _build_auth_user_from_item(rows[0])


def _find_user_by_id_cosmos(user_id: str) -> AuthUser | None:
    from azure.cosmos.exceptions import CosmosHttpResponseError

    container = get_cosmos_container()
    try:
        item = container.read_item(item=f"user::{user_id}", partition_key=f"user::{user_id}")
    except CosmosHttpResponseError:
        return None
    if item.get("deleted") is True:
        return None
    return _build_auth_user_from_item(item)


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


def authenticate_user(db: Session | None, email: str, password: str) -> User | AuthUser | None:
    if _is_cosmos_only_mode():
        user = _find_user_by_email_cosmos(email)
    else:
        managed_db = db or SessionLocal()
        try:
            stmt: Select[tuple[User]] = select(User).where(User.email == email, User.deleted_at.is_(None))
            user = managed_db.execute(stmt).scalar_one_or_none()
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


def get_current_user(credentials: HTTPAuthorizationCredentials | None, db: Session | None) -> User | AuthUser:
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

    if _is_cosmos_only_mode():
        user = _find_user_by_id_cosmos(str(user_id))
    else:
        managed_db = db or SessionLocal()
        try:
            user = managed_db.get(User, user_id)
        finally:
            if db is None:
                managed_db.close()

    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        )

    return user


def register_user(db: Session | None, name: str, email: str, password: str) -> User | AuthUser:
    normalized_name = name.strip()
    normalized_email = email.strip().lower()

    if _is_cosmos_only_mode():
        existing = _find_user_by_email_cosmos(normalized_email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "EMAIL_ALREADY_EXISTS",
                        "message": "Este email ya está registrado",
                    }
                },
            )

        user_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        item = {
            "id": f"user::{user_id}",
            "type": "user",
            "partition_key": f"user::{user_id}",
            "user_id": user_id,
            "name": normalized_name,
            "email": normalized_email,
            "password_hash": get_password_hash(password),
            "created_at": now,
            "updated_at": now,
            "deleted": False,
        }
        get_cosmos_container().upsert_item(item)
        return _build_auth_user_from_item(item)

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
    finally:
        if db is None:
            managed_db.close()
