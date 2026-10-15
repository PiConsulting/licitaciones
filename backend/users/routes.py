import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import update
from sqlalchemy.orm import Session

from infra.config import get_settings
from infra.database import SessionLocal, get_db
from users.management import create_user, get_or_create_sso_user, list_users, update_user
from users.models import SsoLoginCode, User
from users.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    SsoExchangeRequest,
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
from users.sso import (
    DomainNotMappedError,
    SsoCallbackInvalidError,
    SsoMisconfiguredError,
    SsoUpstreamError,
    UnknownTenantError,
    build_authorization_request,
    describe_callback_error,
    exchange_code_for_claims,
)

logger = structlog.get_logger(__name__)

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


@auth_router.get("/sso/{tenant}/login", response_model=None)
def sso_login(tenant: str) -> RedirectResponse | JSONResponse:
    try:
        request = build_authorization_request(tenant)
    except UnknownTenantError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "UNKNOWN_TENANT",
                    "message": "Organización no soportada",
                }
            },
        )
    except SsoMisconfiguredError:
        logger.warning("sso_misconfigured", tenant=tenant)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "SSO_MISCONFIGURED",
                    "message": "El login con Microsoft no está disponible en este momento",
                }
            },
        )

    response = RedirectResponse(url=request.url, status_code=status.HTTP_302_FOUND)
    secure_cookie = get_settings().app_base_url.startswith("https://")
    # Cookie temporal de corta vida; el callback (Historia 25.2) la lee para validar
    # state + PKCE vía MSAL (el `flow` ya incluye el code_verifier generado por MSAL).
    response.set_cookie(
        "sso_flow",
        json.dumps(request.flow),
        max_age=300,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )
    return response


@auth_router.get("/sso/{tenant}/callback", response_model=None)
def sso_callback(
    tenant: str,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse | JSONResponse:
    flow_cookie = request.cookies.get("sso_flow")
    flow = json.loads(flow_cookie) if flow_cookie else None

    try:
        claims = exchange_code_for_claims(tenant, flow, request.query_params)
    except (UnknownTenantError, SsoMisconfiguredError):
        logger.warning("sso_callback_misconfigured", tenant=tenant)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "SSO_MISCONFIGURED",
                    "message": "El login con Microsoft no está disponible en este momento",
                }
            },
        )
    except SsoCallbackInvalidError as exc:
        logger.warning("sso_callback_invalid", tenant=tenant, error_code=exc.error_code)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "SSO_CALLBACK_INVALID",
                    "message": describe_callback_error(exc.error_code),
                }
            },
        )
    except SsoUpstreamError:
        logger.error("sso_upstream_error", tenant=tenant)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": "SSO_UPSTREAM_ERROR",
                    "message": "No se pudo validar el inicio de sesión con Microsoft en este momento. Probá de nuevo en unos minutos.",
                }
            },
        )

    try:
        user = get_or_create_sso_user(db, claims)
    except DomainNotMappedError:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "DOMAIN_NOT_MAPPED",
                    "message": "Tu organización no está habilitada para iniciar sesión",
                }
            },
        )

    login_code = SsoLoginCode(user_id=user.id)
    db.add(login_code)
    db.commit()
    db.refresh(login_code)

    settings = get_settings()
    response = RedirectResponse(
        url=f"{settings.frontend_base_url}/sso/callback?code={login_code.code}",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie("sso_flow")
    return response


@auth_router.post("/sso/exchange", response_model=LoginResponse)
def sso_exchange(
    payload: SsoExchangeRequest, db: Session = Depends(get_db)
) -> LoginResponse | JSONResponse:
    now = datetime.now(UTC)
    # UPDATE condicional atómico: evita que dos requests casi simultáneos canjeen el mismo código.
    result = db.execute(
        update(SsoLoginCode)
        .where(
            SsoLoginCode.code == payload.code,
            SsoLoginCode.used_at.is_(None),
            SsoLoginCode.expires_at > now,
        )
        .values(used_at=now)
    )
    db.commit()

    if result.rowcount == 0:
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content={
                "error": {
                    "code": "SSO_CODE_INVALID",
                    "message": "El código de inicio de sesión expiró o ya fue usado",
                }
            },
        )

    login_code = db.get(SsoLoginCode, payload.code)
    user = db.get(User, login_code.user_id)

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
