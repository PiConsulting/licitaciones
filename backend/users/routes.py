from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from infra.database import SessionLocal, get_db
from users.management import create_user, list_users, update_user
from users.models import User
from users.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from users.service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    http_bearer,
    register_user,
    require_superadmin,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])
protected_router = APIRouter(tags=["protected"])


@auth_router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user = authenticate_user(None, payload.email, payload.password)
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

    with SessionLocal() as db:
        persisted = db.get(User, user.id)
        persisted.last_login_at = datetime.now(UTC)
        db.commit()

    token = create_access_token(user.id)
    return LoginResponse(
        access_token=token,
        name=user.name,
        email=user.email,
        role=user.role,
        business_unit=user.business_unit,
    )


@auth_router.get("/me", response_model=UserResponse)
def me(credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer)) -> UserResponse:
    return UserResponse.model_validate(get_current_user(credentials, None))


@auth_router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> RegisterResponse:
    user = register_user(None, payload.name, payload.email, payload.password)
    return RegisterResponse(id=user.id, email=user.email, name=user.name)


@protected_router.get("/protected-route")
def protected_route(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> dict[str, str]:
    _ = get_current_user(credentials, None)
    return {"status": "ok"}


@users_router.get("", response_model=list[UserResponse])
def get_users(
    _: User = Depends(require_superadmin), db: Session = Depends(get_db)
) -> list[UserResponse]:
    return [UserResponse.model_validate(user) for user in list_users(db)]


@users_router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def post_user(
    payload: UserCreateRequest,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserResponse.model_validate(create_user(db, payload))


@users_router.patch("/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: str,
    payload: UserUpdateRequest,
    actor: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserResponse.model_validate(update_user(db, actor, user_id, payload))
