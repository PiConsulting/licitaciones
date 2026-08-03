from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from shared.config import get_settings
from users.models import User

http_bearer = HTTPBearer(auto_error=False)


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


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    stmt: Select[tuple[User]] = select(User).where(User.email == email, User.deleted_at.is_(None))
    user = db.execute(stmt).scalar_one_or_none()
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


def get_current_user(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User:
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

    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "No autorizado"}},
        )

    return user


def register_user(db: Session, name: str, email: str, password: str) -> User:
    user = User(
        name=name.strip(),
        email=email.strip().lower(),
        password_hash=get_password_hash(password),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "EMAIL_ALREADY_EXISTS",
                    "message": "Este email ya está registrado",
                }
            },
        ) from exc
