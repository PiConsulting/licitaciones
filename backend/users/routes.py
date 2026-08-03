from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.database import get_db
from users.schemas import LoginRequest, LoginResponse
from users.service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    http_bearer,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
protected_router = APIRouter(tags=["protected"])


@auth_router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Email o contraseña incorrectos",
                }
            },
        )

    token = create_access_token(user.id)
    return LoginResponse(access_token=token)


@protected_router.get("/protected-route")
def protected_route(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _ = get_current_user(credentials, db)
    return {"status": "ok"}
