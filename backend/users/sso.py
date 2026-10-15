"""Integración Azure AD / MSAL para login SSO multi-tenant (Historia 25.1).

Dos tenants Azure AD reales y separados (PI y CEDI), cada uno con su propio
App Registration -- no un único tenant multi-dominio. La autoridad de cada
uno es single-tenant (`https://login.microsoftonline.com/{tenant_id}`).

Usa `initiate_auth_code_flow` / `acquire_token_by_auth_code_flow` (no el
par `get_authorization_request_url` / `acquire_token_by_authorization_code`):
ese segundo par es legacy y **descarta en silencio** cualquier kwarg extra
como `code_challenge`/`code_challenge_method` -- causaba
`AADSTS501481: Code_Verifier does not match` en producción porque el PKCE
nunca llegaba a viajar en la URL de autorización real.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

import msal
import structlog

from infra.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
_DEFAULT_SCOPES = ["User.Read"]


class UnknownTenantError(Exception):
    """El `tenant_key` solicitado no es `pi` ni `cedi`."""


class SsoMisconfiguredError(Exception):
    """Faltan variables de configuración requeridas para el tenant solicitado."""


class SsoCallbackInvalidError(Exception):
    """Falta/no coincide el `flow` (cookie), MSAL detecta un `state` inválido, o rechaza
    el intercambio del code (error de protocolo OAuth, p. ej. code inválido/expirado,
    consentimiento requerido, o el usuario canceló el login en Microsoft)."""

    def __init__(self, reason: str, error_code: str | None = None) -> None:
        super().__init__(reason)
        self.error_code = error_code


# Mapeo de códigos de error OAuth/Entra ID (campo "error" de la respuesta de Microsoft)
# a mensajes en español entendibles -- sin esto, el usuario solo ve un mensaje genérico
# sin importar si canceló el login, su cuenta no pertenece al tenant, o el code expiró.
_OAUTH_ERROR_MESSAGES: dict[str, str] = {
    "access_denied": (
        "No se pudo iniciar sesión: tu cuenta de Microsoft no tiene acceso a esta "
        "organización, o cancelaste el inicio de sesión. Verificá que elegiste la "
        "organización correcta (PI o CEDI)."
    ),
    "invalid_grant": "El enlace de inicio de sesión expiró o ya fue usado. Iniciá sesión de nuevo.",
    "consent_required": "Hace falta una aprobación adicional para tu cuenta. Contactá a un administrador.",
    "interaction_required": "Hace falta una aprobación adicional para tu cuenta. Contactá a un administrador.",
    "temporarily_unavailable": "El login con Microsoft no está disponible en este momento. Probá de nuevo en unos minutos.",
}
_DEFAULT_CALLBACK_ERROR_MESSAGE = "No se pudo completar el inicio de sesión con Microsoft."


def describe_callback_error(error_code: str | None) -> str:
    """Traduce el código de error OAuth/Entra ID a un mensaje accionable en español."""
    if error_code and error_code in _OAUTH_ERROR_MESSAGES:
        return _OAUTH_ERROR_MESSAGES[error_code]
    return _DEFAULT_CALLBACK_ERROR_MESSAGE


class SsoUpstreamError(Exception):
    """Falló la comunicación con Microsoft Entra ID durante el canje del code (red, TLS, timeout u otro error inesperado del SDK) -- no es culpa del usuario ni de su `state`/`code`."""


class DomainNotMappedError(Exception):
    """El dominio del email no mapea a ningún `business_unit` conocido y no hay excepción aplicable."""


@dataclass(frozen=True)
class TenantConfig:
    tenant_key: str
    client_id: str
    tenant_id: str
    secret: str

    @property
    def authority(self) -> str:
        return _AUTHORITY_TEMPLATE.format(tenant_id=self.tenant_id)


@dataclass(frozen=True)
class AuthorizationRequest:
    """Resultado de iniciar el flujo: URL de Microsoft + `flow` a persistir (cookie)
    y relayar tal cual al callback (Historia 25.2) -- `flow` ya incluye el `code_verifier`
    generado internamente por MSAL, correlacionado con el `code_challenge` real enviado."""

    url: str
    state: str
    flow: dict[str, Any]


@dataclass(frozen=True)
class SsoClaims:
    """Identidad extraída del `id_token` validado por MSAL en el callback."""

    email: str
    name: str
    tenant_key: str


def _raise_unknown_tenant(tenant_key: str) -> NoReturn:
    raise UnknownTenantError(tenant_key)


def _raise_misconfigured(tenant_key: str) -> NoReturn:
    raise SsoMisconfiguredError(tenant_key)


def _tenant_credentials(settings: Settings, tenant_key: str) -> tuple[str, str, str]:
    if tenant_key == "pi":
        return settings.pi_client_id, settings.pi_tenant_id, settings.pi_secret
    if tenant_key == "cedi":
        return settings.cedi_client_id, settings.cedi_tenant_id, settings.cedi_secret
    _raise_unknown_tenant(tenant_key)


def get_tenant_config(tenant_key: str) -> TenantConfig:
    settings = get_settings()
    client_id, tenant_id, secret = _tenant_credentials(settings, tenant_key)

    if not (client_id and tenant_id and secret and settings.app_base_url):
        _raise_misconfigured(tenant_key)

    return TenantConfig(tenant_key=tenant_key, client_id=client_id, tenant_id=tenant_id, secret=secret)


def _redirect_uri(tenant_key: str) -> str:
    settings = get_settings()
    return f"{settings.app_base_url}/api/v1/auth/sso/{tenant_key}/callback"


def _build_client_app(config: TenantConfig) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        config.client_id,
        authority=config.authority,
        client_credential=config.secret,
    )


def build_authorization_request(tenant_key: str) -> AuthorizationRequest:
    """Arma la URL de autorización de Microsoft Entra ID (Authorization Code + PKCE).

    No valida el callback ni emite ningún JWT -- eso es Historia 25.2.
    """
    config = get_tenant_config(tenant_key)
    client_app = _build_client_app(config)
    flow = client_app.initiate_auth_code_flow(
        _DEFAULT_SCOPES,
        redirect_uri=_redirect_uri(tenant_key),
    )
    return AuthorizationRequest(url=flow["auth_uri"], state=flow["state"], flow=flow)


def exchange_code_for_claims(
    tenant_key: str,
    flow: dict[str, Any] | None,
    auth_response: Mapping[str, str],
) -> SsoClaims:
    """Valida el callback (vía MSAL, state + PKCE incluidos) y canjea el `code` por el
    `id_token` (Historia 25.2).

    `flow` viene de la cookie que `build_authorization_request` (Historia 25.1) dejó en
    el navegador -- no de almacenamiento server-side. `auth_response` es el querystring
    completo que Microsoft agregó al redirigir de vuelta (`code`, `state`, o `error`).
    """
    if not flow:
        raise SsoCallbackInvalidError("missing_flow_cookie")

    config = get_tenant_config(tenant_key)
    client_app = _build_client_app(config)

    try:
        result = client_app.acquire_token_by_auth_code_flow(flow, dict(auth_response))
    except ValueError as exc:
        # MSAL valida state/flow localmente antes de pegarle a Microsoft (p. ej.
        # "state mismatch", "state missing from auth_code_flow").
        logger.warning("sso_callback_invalid", tenant=tenant_key, reason=str(exc))
        raise SsoCallbackInvalidError(str(exc)) from exc
    except Exception as exc:
        # Red/TLS/timeout u otro fallo inesperado del SDK hablando con Microsoft --
        # no debe filtrarse como 500 genérico; se loguea completo para diagnóstico.
        logger.exception("sso_token_exchange_failed", tenant=tenant_key)
        raise SsoUpstreamError("token_exchange_failed") from exc

    if "error" in result:
        error_code = result.get("error")
        logger.warning(
            "sso_token_exchange_rejected",
            tenant=tenant_key,
            error=error_code,
            error_description=result.get("error_description"),
        )
        raise SsoCallbackInvalidError(
            result.get("error_description", error_code), error_code=error_code
        )

    claims = result.get("id_token_claims") or {}
    email = claims.get("preferred_username") or claims.get("email")
    if not email:
        raise SsoCallbackInvalidError("missing_email_claim")

    name = claims.get("name") or email
    return SsoClaims(email=email, name=name, tenant_key=tenant_key)

