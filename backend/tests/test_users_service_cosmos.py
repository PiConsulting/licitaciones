"""Cobertura de `users/service.py` en modo cosmos_only.

FIX (auditoría 2026-08-12, flujo Cosmos): antes de esta auditoría no existía
ningún test para el camino de autenticación en modo Cosmos -- el bug de
`_find_user_by_id_cosmos` tratando CUALQUIER error de Cosmos (throttling,
outage) como "usuario no encontrado" pasó completamente inadvertido porque
nada ejercitaba ese código."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import users.service as users_service
from shared.config import get_settings


def test_get_current_user_cosmos_only_resuelve_usuario_real(cosmos_only) -> None:
    """Camino feliz: con el token de un usuario real seedeado en el fake
    container, get_current_user debe devolver ese usuario."""
    _container, user_id, token = cosmos_only

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = users_service.get_current_user(credentials, db=None)

    assert user.id == user_id


def test_get_current_user_cosmos_only_404_real_es_401(cosmos_only) -> None:
    """Si Cosmos responde 404 real (el usuario no existe / fue borrado),
    sigue siendo un 401 -- comportamiento sin cambios."""
    from users.service import create_access_token

    token_de_usuario_inexistente = create_access_token("00000000-0000-0000-0000-000000000000")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_de_usuario_inexistente)

    with pytest.raises(HTTPException) as exc_info:
        users_service.get_current_user(credentials, db=None)

    assert exc_info.value.status_code == 401


def test_get_current_user_cosmos_only_error_transitorio_no_es_401(
    cosmos_only, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX: un error transitorio de Cosmos (throttling/outage) NO debe
    deslogear al usuario -- antes `_find_user_by_id_cosmos` atrapaba
    CosmosHttpResponseError en general (la clase base de TODOS los errores
    HTTP de Cosmos, no solo 404) y devolvía None, indistinguible de un token
    invalido. Ahora tiene que propagarse como 503, no como 401."""
    from azure.cosmos.exceptions import CosmosHttpResponseError

    container, user_id, token = cosmos_only

    def _raise_throttled(*args, **kwargs):
        raise CosmosHttpResponseError(message="Request rate is large", status_code=429)

    monkeypatch.setattr(container, "read_item", Mock(side_effect=_raise_throttled))

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        users_service.get_current_user(credentials, db=None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"]["code"] == "AUTH_BACKEND_UNAVAILABLE"


def test_find_user_by_id_cosmos_usuario_borrado_logicamente_es_none(cosmos_only) -> None:
    """Un usuario con `deleted=True` en Cosmos tiene que resolver a None (no
    autenticado), aunque el read_item si encuentre el documento."""
    container, user_id, _token = cosmos_only

    stored_key = f"user::{user_id}"
    container.items[stored_key]["deleted"] = True

    result = users_service._find_user_by_id_cosmos(user_id)

    assert result is None
