import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_backend.db"
os.environ["SECRET_KEY"] = "this-is-a-long-test-secret-key-32bytes"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_HOURS"] = "24"
os.environ["APP_ENV"] = "production"

from infra.config import get_settings
from infra.database import Base, SessionLocal, engine
from main import app
from users.models import User
from users.service import create_access_token, get_password_hash


@pytest.fixture(autouse=True)
def setup_db():
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        User(
            email="test@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Test User",
        )
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _real_postgres_url() -> str | None:
    """La URL de Postgres local real, leída directo de `.env` (no de
    `os.environ`, que este conftest ya pisó con la URL de SQLite arriba).
    Usada por tests que necesitan Postgres real (pgvector, constraints FK
    que SQLite no aplica por default) -- Historias 22.3+."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return None
    values = dotenv_values(env_path)
    url = values.get("DATABASE_URL")
    return url if url and url.startswith("postgresql") else None


@pytest.fixture
def pg_session_factory():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session, sessionmaker

    url = _real_postgres_url()
    if not url:
        pytest.skip("DATABASE_URL de Postgres local no configurada en .env")
    pg_engine = create_engine(url, future=True)
    try:
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No se pudo conectar a Postgres local: {exc}")
    factory = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False, class_=Session)
    yield factory
    pg_engine.dispose()


@pytest.fixture
def auth_token() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    token = create_access_token(user.id)
    db.close()
    return token
