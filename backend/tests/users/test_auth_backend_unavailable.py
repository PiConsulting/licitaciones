"""AC3 (Historia 22.9): un fallo de conexión a Postgres en auth se distingue
de "usuario no encontrado" -- reemplaza la cobertura equivalente que existía
para el camino Cosmos (`test_users_service_cosmos.py`, eliminado junto con
esa rama en esta historia)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import OperationalError

import users.service as users_service


def _fake_operational_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_get_current_user_connection_failure_is_503(auth_token: str) -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_token)

    with patch("users.service.SessionLocal") as mock_session_local:
        mock_session_local.return_value.get.side_effect = _fake_operational_error()

        with pytest.raises(HTTPException) as exc_info:
            users_service.get_current_user(credentials, db=None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"]["code"] == "AUTH_BACKEND_UNAVAILABLE"


def test_get_current_user_unknown_user_is_still_401(auth_token: str) -> None:
    """Camino feliz de "no encontrado" (sin fallo de conexión): sigue 401,
    sin cambios -- no debe confundirse con AUTH_BACKEND_UNAVAILABLE."""
    token_de_usuario_inexistente = users_service.create_access_token(
        "00000000-0000-0000-0000-000000000000"
    )
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=token_de_usuario_inexistente
    )

    with pytest.raises(HTTPException) as exc_info:
        users_service.get_current_user(credentials, db=None)

    assert exc_info.value.status_code == 401


def test_authenticate_user_connection_failure_is_503() -> None:
    with patch("users.service.SessionLocal") as mock_session_local:
        mock_session_local.return_value.execute.side_effect = _fake_operational_error()

        with pytest.raises(HTTPException) as exc_info:
            users_service.authenticate_user(None, "test@cedia.com", "Test1234!")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"]["code"] == "AUTH_BACKEND_UNAVAILABLE"
