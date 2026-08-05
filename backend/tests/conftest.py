import os

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_backend.db"
os.environ["SECRET_KEY"] = "this-is-a-long-test-secret-key-32bytes"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_HOURS"] = "24"
os.environ["APP_ENV"] = "development"
os.environ["USE_LOCAL_ADAPTERS"] = "true"
os.environ["PERSISTENCE_MODE"] = "sql"

from main import app
from shared.config import get_settings
from shared.database import Base, SessionLocal, engine
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


@pytest.fixture
def auth_token() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    token = create_access_token(user.id)
    db.close()
    return token
