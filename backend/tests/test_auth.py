def test_login_success(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@cedia.com", "password": "Test1234!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@cedia.com", "password": "WrongPassword1"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email o contraseña incorrectos"


def test_protected_endpoint_without_token(client):
    response = client.get("/api/v1/protected-route")
    assert response.status_code == 401


def test_protected_endpoint_with_valid_token(client, auth_token):
    response = client.get(
        "/api/v1/protected-route",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
