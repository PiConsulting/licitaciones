"""Tests de la Historia 25.1: configuración multi-tenant SSO + endpoint de inicio de sesión.

`msal.ConfidentialClientApplication` se mockea en todos los tests: construir la URL de
autorización no debe depender de red real ni de tenants/credenciales Azure AD reales.
"""

import secrets

import pytest

from infra.config import get_settings
from users import sso


class _FakeConfidentialClientApplication:
    """Reemplazo de `msal.ConfidentialClientApplication` para no pegarle a Azure real.

    Imita `initiate_auth_code_flow` (API soportada, maneja PKCE internamente) -- NO el
    par legacy `get_authorization_request_url`/`acquire_token_by_authorization_code`,
    que descarta en silencio kwargs como `code_challenge` (causa real de
    AADSTS501481 en producción, ver sso.py).
    """

    last_call: dict | None = None

    def __init__(self, client_id, authority=None, client_credential=None):
        self.client_id = client_id
        self.authority = authority
        self.client_credential = client_credential

    def initiate_auth_code_flow(self, scopes, redirect_uri=None, **kwargs):
        state = secrets.token_urlsafe(16)
        code_verifier = secrets.token_urlsafe(32)
        flow = {
            "state": state,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "code_verifier": code_verifier,
            "auth_uri": (
                f"{self.authority}/oauth2/v2.0/authorize"
                f"?client_id={self.client_id}"
                f"&state={state}"
                f"&redirect_uri={redirect_uri}"
                f"&code_challenge=fake-challenge-for-{code_verifier}"
                "&code_challenge_method=S256"
            ),
        }
        type(self).last_call = {
            "client_id": self.client_id,
            "authority": self.authority,
            "scopes": scopes,
            "redirect_uri": redirect_uri,
            "flow": flow,
        }
        return flow


@pytest.fixture(autouse=True)
def _fake_msal(monkeypatch):
    monkeypatch.setattr(sso.msal, "ConfidentialClientApplication", _FakeConfidentialClientApplication)
    yield
    _FakeConfidentialClientApplication.last_call = None


def _set_tenant_env(
    monkeypatch,
    tenant_key: str,
    *,
    client_id: str = "client-id",
    tenant_id: str = "tenant-id",
    secret: str = "super-secret",
    app_base_url: str = "http://localhost:8000",
) -> None:
    prefix = tenant_key.upper()
    monkeypatch.setenv(f"{prefix}_CLIENT_ID", client_id)
    monkeypatch.setenv(f"{prefix}_TENANT_ID", tenant_id)
    monkeypatch.setenv(f"{prefix}_SECRET", secret)
    monkeypatch.setenv("APP_BASE_URL", app_base_url)
    get_settings.cache_clear()


# --- get_tenant_config / build_authorization_request (unitarios) ---------------------


def test_get_tenant_config_unknown_tenant_raises():
    with pytest.raises(sso.UnknownTenantError):
        sso.get_tenant_config("korex")


def test_get_tenant_config_missing_vars_raises(monkeypatch):
    monkeypatch.setenv("PI_CLIENT_ID", "")
    monkeypatch.setenv("PI_TENANT_ID", "")
    monkeypatch.setenv("PI_SECRET", "")
    get_settings.cache_clear()

    with pytest.raises(sso.SsoMisconfiguredError):
        sso.get_tenant_config("pi")


def test_get_tenant_config_resolves_pi(monkeypatch):
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    config = sso.get_tenant_config("pi")

    assert config.tenant_key == "pi"
    assert config.tenant_id == "pi-tenant-123"
    assert config.authority == "https://login.microsoftonline.com/pi-tenant-123"


def test_build_authorization_request_contains_tenant_and_state(monkeypatch):
    _set_tenant_env(monkeypatch, "cedi", tenant_id="cedi-tenant-456")

    request = sso.build_authorization_request("cedi")

    assert "cedi-tenant-456" in request.url
    assert request.state in request.url
    assert len(request.state) >= 20
    assert request.flow["code_verifier"]  # MSAL lo genera internamente, no nosotros
    assert request.flow["state"] == request.state


def test_build_authorization_request_uses_pkce_and_correct_redirect_uri(monkeypatch):
    _set_tenant_env(monkeypatch, "pi")

    request = sso.build_authorization_request("pi")
    call = _FakeConfidentialClientApplication.last_call

    assert "code_challenge=" in request.url
    assert "code_challenge_method=S256" in request.url
    assert call["redirect_uri"] == "http://localhost:8000/api/v1/auth/sso/pi/callback"
    assert call["scopes"] == ["User.Read"]


def test_build_authorization_request_unknown_tenant_raises():
    with pytest.raises(sso.UnknownTenantError):
        sso.build_authorization_request("korex")


# --- GET /api/v1/auth/sso/{tenant}/login (integración) -------------------------------


def test_sso_login_redirects_to_microsoft_with_state_cookies(client, monkeypatch):
    _set_tenant_env(monkeypatch, "pi", tenant_id="pi-tenant-123")

    response = client.get("/api/v1/auth/sso/pi/login", follow_redirects=False)

    assert response.status_code == 302
    assert "pi-tenant-123" in response.headers["location"]
    assert "sso_flow" in response.cookies


def test_sso_login_unknown_tenant_returns_404(client):
    response = client.get("/api/v1/auth/sso/korex/login", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_TENANT"


def test_sso_login_misconfigured_returns_503(client, monkeypatch):
    monkeypatch.setenv("CEDI_CLIENT_ID", "")
    monkeypatch.setenv("CEDI_TENANT_ID", "")
    monkeypatch.setenv("CEDI_SECRET", "")
    get_settings.cache_clear()

    response = client.get("/api/v1/auth/sso/cedi/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SSO_MISCONFIGURED"


def test_sso_login_does_not_affect_existing_password_login(client):
    """Guardrail: esta historia no debe romper el login existente (AC compartido con Épica)."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@cedia.com", "password": "Test1234!"},
    )

    assert response.status_code == 200
