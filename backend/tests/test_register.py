from shared.database import SessionLocal
from users.models import User


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Juan Perez",
            "email": "juan.perez@example.com",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["email"] == "juan.perez@example.com"
    assert data["name"] == "Juan Perez"
    assert "password_hash" not in data

    db = SessionLocal()
    user = db.query(User).filter_by(email="juan.perez@example.com").first()
    assert user is not None
    assert user.password_hash != "SecurePass123"
    db.close()


def test_register_duplicate_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Otro Usuario",
            "email": "test@cedia.com",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "EMAIL_ALREADY_EXISTS"
    assert "registrado" in data["error"]["message"].lower()


def test_register_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Juan Perez",
            "email": "not-an-email",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 422


def test_register_weak_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Juan Perez",
            "email": "juan@example.com",
            "password": "OnlyLetters",
        },
    )

    assert response.status_code == 422


def test_register_missing_fields(client):
    response = client.post("/api/v1/auth/register", json={})
    assert response.status_code == 422


def test_register_password_too_short(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Juan Perez",
            "email": "juan2@example.com",
            "password": "Short1",
        },
    )
    assert response.status_code == 422


def test_register_password_no_number(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Juan Perez",
            "email": "juan3@example.com",
            "password": "NoNumberPassword",
        },
    )
    assert response.status_code == 422


def test_register_name_empty(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "   ",
            "email": "juan4@example.com",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 422
