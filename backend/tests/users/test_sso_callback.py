"""Tests de la Historia 25.2: callback SSO, mapeo de dominio, JIT provisioning
y código de intercambio de un solo uso.

`msal.ConfidentialClientApplication` se mockea (construcción de URL y canje de code),
no se pega a Azure real en ningún test.
"""

import secrets
from urllib.parse import parse_qs, urlparse

import pytest

from infra.business_units import business_unit_for_email_domain
from infra.config import get_settings
from infra.database import SessionLocal
from users import sso
from users.management import get_or_create_sso_user
from users.models import User
from users.roles import UserRole


class _FakeConfidentialClientApplication:
    """Reemplazo de `msal.ConfidentialClientApplication` para no pegarle a Azure real.

    Imita `initiate_auth_code_flow`/`acquire_token_by_auth_code_flow` (API soportada) --
    NO el par legacy que descarta en silencio el PKCE (ver sso.py, AADSTS501481).
    """

    last_call: dict | None = None
    next_token_result: dict | None = None
    next_token_exception: Exception | None = None

    def __init__(self, client_id, authority=None, client_credential=None):
        self.client_id = client_id
        self.authority = authority
        self.client_credential = client_credential

    def initiate_auth_code_flow(self, scopes, redirect_uri=None, **kwargs):
        state = secrets.token_urlsafe(16)
        flow = {
            "state": state,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "code_verifier": secrets.token_urlsafe(32),
            "auth_uri": (
                f"{self.authority}/oauth2/v2.0/authorize"
                f"?state={state}&redirect_uri={redirect_uri}"
            ),
        }
        type(self).last_call = {"client_id": self.client_id, "scopes": scopes, "flow": flow}
        return flow

    def acquire_token_by_auth_code_flow(self, auth_code_flow, auth_response, scopes=None):
        if auth_code_flow.get("state") != auth_response.get("state"):
            raise ValueError("state mismatch")
        if type(self).next_token_exception is not None:
            raise type(self).next_token_exception
        return type(self).next_token_result


@pytest.fixture(autouse=True)
def _fake_msal(monkeypatch):
    monkeypatch.setattr(sso.msal, "ConfidentialClientApplication", _FakeConfidentialClientApplication)
    yield
    _FakeConfidentialClientApplication.last_call = None
    _FakeConfidentialClientApplication.next_token_result = None
    _FakeConfidentialClientApplication.next_token_exception = None


def _set_tenant_env(monkeypatch, tenant_key: str, *, tenant_id: str = "tenant-id") -> None:
    prefix = tenant_key.upper()
    monkeypatch.setenv(f"{prefix}_CLIENT_ID", "client-id")
    monkeypatch.setenv(f"{prefix}_TENANT_ID", tenant_id)
    monkeypatch.setenv(f"{prefix}_SECRET", "super-secret")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:5173")
    get_settings.cache_clear()


# --- business_unit_for_email_domain ---------------------------------------------------


def test_business_unit_for_email_domain_known():
    assert business_unit_for_email_domain("ana@piconsulting.com.ar") == "PI"
    assert business_unit_for_email_domain("ana@CEDI.com.ar") == "CEDI"
    assert business_unit_for_email_domain("ana@wemox.com.ar") == "Wemox"
    assert business_unit_for_email_domain("ana@vulps.com.ar") == "Vulps"


def test_business_unit_for_email_domain_unknown_returns_none():
    assert business_unit_for_email_domain("ana@korex.com.ar") is None
    assert business_unit_for_email_domain("ana@otrodominio.com") is None


# --- get_or_create_sso_user (JIT provisioning + excepciones) --------------------------


def test_get_or_create_sso_user_jit_creates_member(monkeypatch):
    monkeypatch.setenv("SSO_SUPERADMIN_EMAILS", "")
    get_settings.cache_clear()
    claims = sso.SsoClaims(email="nuevo@piconsulting.com.ar", name="Nuevo Usuario", tenant_key="pi")

    with SessionLocal() as db:
        user = get_or_create_sso_user(db, claims)

        assert user.role == UserRole.MIEMBRO.value
        assert user.business_unit == "PI"
        assert user.email == "nuevo@piconsulting.com.ar"
        assert user.password_hash  # poblado, aunque no usable como password real


def test_get_or_create_sso_user_exception_email_creates_superadmin(monkeypatch):
    monkeypatch.setenv("SSO_SUPERADMIN_EMAILS", "agostina.torres@piconsulting.com.ar")
    get_settings.cache_clear()
    claims = sso.SsoClaims(
        email="agostina.torres@piconsulting.com.ar", name="Agostina Torres", tenant_key="pi"
    )

    with SessionLocal() as db:
        user = get_or_create_sso_user(db, claims)

        assert user.role == UserRole.SUPERADMIN.value
        assert user.business_unit == "PI"


def test_get_or_create_sso_user_promotes_existing_user_in_exception_list(monkeypatch):
    monkeypatch.setenv("SSO_SUPERADMIN_EMAILS", "promovido@piconsulting.com.ar")
    get_settings.cache_clear()

    with SessionLocal() as db:
        db.add(
            User(
                email="promovido@piconsulting.com.ar",
                password_hash="x",
                name="Promovido",
                role=UserRole.MIEMBRO.value,
                business_unit="PI",
            )
        )
        db.commit()

    claims = sso.SsoClaims(email="promovido@piconsulting.com.ar", name="Promovido", tenant_key="pi")
    with SessionLocal() as db:
        user = get_or_create_sso_user(db, claims)
        assert user.role == UserRole.SUPERADMIN.value


def test_get_or_create_sso_user_rejects_unmapped_domain_without_exception(monkeypatch):
    monkeypatch.setenv("SSO_SUPERADMIN_EMAILS", "")
    get_settings.cache_clear()
    claims = sso.SsoClaims(email="alguien@korex.com.ar", name="Alguien", tenant_key="cedi")

    with SessionLocal() as db, pytest.raises(sso.DomainNotMappedError):
        get_or_create_sso_user(db, claims)


def test_get_or_create_sso_user_rejects_suspended_existing_user(monkeypatch):
    monkeypatch.setenv("SSO_SUPERADMIN_EMAILS", "")
    get_settings.cache_clear()

    with SessionLocal() as db:
        db.add(
            User(
                email="suspendido@piconsulting.com.ar",
                password_hash="x",
                name="Suspendido",
                role=UserRole.MIEMBRO.value,
                business_unit="PI",
                is_active=False,
            )
        )
        db.commit()

    claims = sso.SsoClaims(email="suspendido@piconsulting.com.ar", name="Suspendido", tenant_key="pi")
    with SessionLocal() as db:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_or_create_sso_user(db, claims)
        assert exc_info.value.status_code == 403


# --- GET /api/v1/auth/sso/{tenant}/callback + POST /api/v1/auth/sso/exchange ----------


def test_sso_callback_token_exchange_raises_returns_502_not_500(client, monkeypatch):
    """Regresión: un fallo inesperado del SDK/red hablando con Microsoft (p. ej. un
    `code` inválido/expirado, timeout o error TLS) no debe filtrarse como 500 genérico."""
    _set_tenant_env(monkeypatch, "cedi", tenant_id="cedi-tenant-789")

    login_response = client.get("/api/v1/auth/sso/cedi/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _FakeConfidentialClientApplication.next_token_exception = RuntimeError("connection reset")

    response = client.get(
        f"/api/v1/auth/sso/cedi/callback?code=cualquier-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "SSO_UPSTREAM_ERROR"


def test_sso_callback_microsoft_rejects_code_returns_400(client, monkeypatch):
    """MSAL reporta un error de protocolo OAuth (p. ej. `invalid_grant`) como dict, sin excepción."""
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    login_response = client.get("/api/v1/auth/sso/pi/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _FakeConfidentialClientApplication.next_token_result = {
        "error": "invalid_grant",
        "error_description": "AADSTS70008: El code expiró o ya fue usado.",
    }

    response = client.get(
        f"/api/v1/auth/sso/pi/callback?code=code-ya-usado&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SSO_CALLBACK_INVALID"
    assert "expiró" in response.json()["error"]["message"]


def test_sso_callback_access_denied_shows_specific_message(client, monkeypatch):
    """El usuario no pertenece al tenant o canceló el login -- no debe verse como un
    error genérico de sistema, sino un mensaje que lo oriente a elegir bien la org."""
    _set_tenant_env(monkeypatch, "cedi", tenant_id="cedi-tenant-789")

    login_response = client.get("/api/v1/auth/sso/cedi/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _FakeConfidentialClientApplication.next_token_result = {
        "error": "access_denied",
        "error_description": "AADSTS50020: user account does not exist in tenant.",
    }

    response = client.get(
        f"/api/v1/auth/sso/cedi/callback?code=cualquiera&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 400
    message = response.json()["error"]["message"]
    assert "no tiene acceso a esta organización" in message


def test_sso_callback_unmapped_oauth_error_falls_back_to_generic_message(client, monkeypatch):
    """Un error de Microsoft que no está en nuestro mapeo no debe filtrar texto técnico crudo."""
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    login_response = client.get("/api/v1/auth/sso/pi/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _FakeConfidentialClientApplication.next_token_result = {
        "error": "unsupported_response_type",
        "error_description": "AADSTS9002313: algún detalle técnico interno.",
    }

    response = client.get(
        f"/api/v1/auth/sso/pi/callback?code=cualquiera&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "No se pudo completar el inicio de sesión con Microsoft."


def test_sso_callback_unknown_tenant_returns_503(client, monkeypatch):
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    # state/cookies válidos (del login de "pi") pero tenant desconocido en la URL del callback:
    # la validación de state pasa, y recién ahí get_tenant_config("korex") revienta.
    login_response = client.get("/api/v1/auth/sso/pi/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    response = client.get(
        f"/api/v1/auth/sso/korex/callback?code=abc&state={state}", follow_redirects=False
    )
    assert response.status_code == 503


def test_sso_callback_missing_state_cookie_returns_400(client, monkeypatch):
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    response = client.get(
        "/api/v1/auth/sso/pi/callback?code=abc&state=xyz", follow_redirects=False
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SSO_CALLBACK_INVALID"


def test_sso_callback_full_flow_issues_jwt_and_code_is_single_use(client, monkeypatch):
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    login_response = client.get("/api/v1/auth/sso/pi/login", follow_redirects=False)
    assert login_response.status_code == 302
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _FakeConfidentialClientApplication.next_token_result = {
        "id_token_claims": {
            "preferred_username": "nueva.persona@piconsulting.com.ar",
            "name": "Nueva Persona",
        }
    }

    callback_response = client.get(
        f"/api/v1/auth/sso/pi/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )

    assert callback_response.status_code == 302
    location = callback_response.headers["location"]
    assert location.startswith("http://localhost:5173/sso/callback?code=")
    exchange_code = location.split("code=", 1)[1]

    exchange_response = client.post("/api/v1/auth/sso/exchange", json={"code": exchange_code})
    assert exchange_response.status_code == 200
    data = exchange_response.json()
    assert data["email"] == "nueva.persona@piconsulting.com.ar"
    assert data["role"] == "miembro"
    assert data["business_unit"] == "PI"
    assert "access_token" in data

    reuse_response = client.post("/api/v1/auth/sso/exchange", json={"code": exchange_code})
    assert reuse_response.status_code == 410
    assert reuse_response.json()["error"]["code"] == "SSO_CODE_INVALID"


def test_sso_exchange_unknown_code_returns_410(client):
    response = client.post("/api/v1/auth/sso/exchange", json={"code": "no-existe"})
    assert response.status_code == 410
