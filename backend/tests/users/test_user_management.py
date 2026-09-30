from fastapi.testclient import TestClient

from infra.business_units import BUSINESS_UNITS
from infra.database import SessionLocal
from users.models import User
from users.roles import UserRole
from users.service import create_access_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides) -> dict:
    payload = {
        "name": "Nuevo Usuario",
        "email": "nuevo@cedia.com",
        "business_unit": BUSINESS_UNITS[1],
        "role": UserRole.MIEMBRO.value,
        "is_active": True,
        "password": "Clave1234",
    }
    payload.update(overrides)
    return payload


def _user_id(email: str) -> str:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).one().id


def test_login_returns_role_and_business_unit(client: TestClient):
    response = client.post(
        "/api/v1/auth/login", json={"email": "test@cedia.com", "password": "Test1234!"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.SUPERADMIN.value
    assert response.json()["business_unit"] == BUSINESS_UNITS[0]


def test_login_updates_last_login(client: TestClient, auth_token: str):
    before = client.get("/api/v1/users", headers=_headers(auth_token)).json()[0]
    assert before["last_login_at"] is None

    client.post("/api/v1/auth/login", json={"email": "test@cedia.com", "password": "Test1234!"})

    after = client.get("/api/v1/users", headers=_headers(auth_token)).json()[0]
    assert after["last_login_at"] is not None


def test_me_returns_current_profile(client: TestClient, member_token: str):
    response = client.get("/api/v1/auth/me", headers=_headers(member_token))

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.MIEMBRO.value
    assert response.json()["business_unit"] == BUSINESS_UNITS[0]


def test_member_cannot_access_user_endpoints(client: TestClient, member_token: str):
    headers = _headers(member_token)
    target = _user_id("test@cedia.com")

    responses = [
        client.get("/api/v1/users", headers=headers),
        client.post("/api/v1/users", headers=headers, json=_payload()),
        client.patch(f"/api/v1/users/{target}", headers=headers, json={"name": "X"}),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert response.json()["error"]["message"]


def test_user_endpoints_require_authentication(client: TestClient):
    assert client.get("/api/v1/users").status_code == 401


def test_superadmin_lists_users(client: TestClient, auth_token: str, member_token: str):
    response = client.get("/api/v1/users", headers=_headers(auth_token))

    assert response.status_code == 200
    emails = {item["email"] for item in response.json()}
    assert emails == {"test@cedia.com", "miembro@cedia.com"}
    assert "password_hash" not in response.json()[0]


def test_superadmin_creates_user_who_can_login(client: TestClient, auth_token: str):
    created = client.post("/api/v1/users", headers=_headers(auth_token), json=_payload())

    assert created.status_code == 201
    body = created.json()
    assert body["role"] == UserRole.MIEMBRO.value
    assert body["business_unit"] == BUSINESS_UNITS[1]
    assert body["is_active"] is True

    login = client.post(
        "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "Clave1234"}
    )
    assert login.status_code == 200
    assert login.json()["business_unit"] == BUSINESS_UNITS[1]


def test_create_user_duplicate_email_conflicts(client: TestClient, auth_token: str):
    client.post("/api/v1/users", headers=_headers(auth_token), json=_payload())

    response = client.post("/api/v1/users", headers=_headers(auth_token), json=_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_create_user_rejects_unknown_business_unit_and_weak_password(
    client: TestClient, auth_token: str
):
    headers = _headers(auth_token)

    assert (
        client.post(
            "/api/v1/users", headers=headers, json=_payload(business_unit="Inexistente")
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/users", headers=headers, json=_payload(password="corta")).status_code
        == 422
    )
    assert (
        client.post("/api/v1/users", headers=headers, json=_payload(role="otro")).status_code
        == 422
    )


def test_every_catalog_unit_can_be_assigned(client: TestClient, auth_token: str):
    for index, unit in enumerate(BUSINESS_UNITS):
        response = client.post(
            "/api/v1/users",
            headers=_headers(auth_token),
            json=_payload(email=f"unidad{index}@cedia.com", business_unit=unit.lower()),
        )
        assert response.status_code == 201
        assert response.json()["business_unit"] == unit


def test_superadmin_edits_unit_role_and_password(client: TestClient, auth_token: str):
    user_id = client.post(
        "/api/v1/users", headers=_headers(auth_token), json=_payload()
    ).json()["id"]

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_headers(auth_token),
        json={
            "business_unit": BUSINESS_UNITS[2],
            "role": UserRole.SUPERADMIN.value,
            "password": "OtraClave99",
        },
    )

    assert response.status_code == 200
    assert response.json()["business_unit"] == BUSINESS_UNITS[2]
    assert response.json()["role"] == UserRole.SUPERADMIN.value
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "Clave1234"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "OtraClave99"}
        ).status_code
        == 200
    )


def test_empty_password_on_edit_keeps_current_password(client: TestClient, auth_token: str):
    user_id = client.post(
        "/api/v1/users", headers=_headers(auth_token), json=_payload()
    ).json()["id"]

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_headers(auth_token),
        json={"name": "Renombrado", "password": ""},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renombrado"
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "Clave1234"}
        ).status_code
        == 200
    )


def test_edit_email_to_existing_one_conflicts(client: TestClient, auth_token: str):
    user_id = client.post(
        "/api/v1/users", headers=_headers(auth_token), json=_payload()
    ).json()["id"]

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_headers(auth_token),
        json={"email": "test@cedia.com"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_edit_unknown_user_returns_404(client: TestClient, auth_token: str):
    response = client.patch(
        "/api/v1/users/no-existe", headers=_headers(auth_token), json={"name": "X"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_suspended_user_cannot_login_nor_use_open_session(
    client: TestClient, auth_token: str
):
    user_id = client.post(
        "/api/v1/users", headers=_headers(auth_token), json=_payload()
    ).json()["id"]
    open_session = create_access_token(user_id)
    assert client.get("/api/v1/auth/me", headers=_headers(open_session)).status_code == 200

    client.patch(f"/api/v1/users/{user_id}", headers=_headers(auth_token), json={"is_active": False})

    login = client.post(
        "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "Clave1234"}
    )
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "USER_SUSPENDED"
    session = client.get("/api/v1/auth/me", headers=_headers(open_session))
    assert session.status_code == 401
    assert session.json()["error"]["code"] == "USER_SUSPENDED"


def test_reactivated_user_can_login_again(client: TestClient, auth_token: str):
    user_id = client.post(
        "/api/v1/users", headers=_headers(auth_token), json=_payload(is_active=False)
    ).json()["id"]

    client.patch(f"/api/v1/users/{user_id}", headers=_headers(auth_token), json={"is_active": True})

    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "nuevo@cedia.com", "password": "Clave1234"}
        ).status_code
        == 200
    )


def test_superadmin_cannot_remove_own_role_nor_suspend_self(
    client: TestClient, auth_token: str
):
    own_id = _user_id("test@cedia.com")
    headers = _headers(auth_token)

    demote = client.patch(
        f"/api/v1/users/{own_id}", headers=headers, json={"role": UserRole.MIEMBRO.value}
    )
    suspend = client.patch(f"/api/v1/users/{own_id}", headers=headers, json={"is_active": False})
    rename = client.patch(f"/api/v1/users/{own_id}", headers=headers, json={"name": "Yo"})

    assert demote.status_code == 409
    assert demote.json()["error"]["code"] == "SELF_ROLE_CHANGE_FORBIDDEN"
    assert suspend.status_code == 409
    assert suspend.json()["error"]["code"] == "SELF_SUSPEND_FORBIDDEN"
    assert rename.status_code == 200
