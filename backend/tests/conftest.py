import os
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_backend.db"
os.environ["SECRET_KEY"] = "this-is-a-long-test-secret-key-32bytes"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_HOURS"] = "24"
os.environ["APP_ENV"] = "production"
os.environ["PERSISTENCE_MODE"] = "sql"

import users.service as users_service
from analysis import cosmos_runtime
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


class FakeCosmosContainer:
    """Minimal in-memory stand-in for the handful of query shapes this codebase issues.

    FIX (auditoría 2026-08-12, hallazgo #6 -- concurrencia optimista): antes
    esta fake no simulaba `_etag` para nada, así que ningún test podía
    ejercitar la protección de concurrencia optimista de `_upsert_analysis`
    en `cosmos_runtime.py`. Ahora cada escritura recibe un `_etag` nuevo (como
    hace Cosmos real) y `replace_item` respeta `match_condition`, así que un
    write con un etag desactualizado falla con `CosmosAccessConditionFailedError`
    (412) en vez de pisar en silencio un cambio concurrente.
    """

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self._etag_counter = 0

    def _next_etag(self) -> str:
        self._etag_counter += 1
        return f"fake-etag-{self._etag_counter}"

    def add(self, item: dict) -> None:
        self.items[item["id"]] = item

    def upsert_item(self, item):
        # Real azure-cosmos upsert_item has no partition_key kwarg (it infers the
        # value from the body) — omitting it here catches accidental partition_key=
        # kwargs the way the real SDK would (it crashes deep in the transport layer).
        stored = dict(item)
        stored["_etag"] = self._next_etag()
        self.items[item["id"]] = stored
        return stored

    def replace_item(self, item, body, etag=None, match_condition=None, **kwargs):
        from azure.cosmos.exceptions import CosmosAccessConditionFailedError, CosmosResourceNotFoundError

        item_id = item if isinstance(item, str) else item.get("id")
        current = self.items.get(item_id)
        if current is None:
            raise CosmosResourceNotFoundError(status_code=404, message="not found")
        if match_condition is not None and etag is not None and current.get("_etag") != etag:
            raise CosmosAccessConditionFailedError(
                status_code=412,
                message="etag mismatch: el item cambio desde que se leyo",
            )
        stored = dict(body)
        stored["_etag"] = self._next_etag()
        self.items[item_id] = stored
        return stored

    def delete_item(self, item, partition_key=None):
        stored = self.items.get(item)
        if stored is None:
            return
        if partition_key is not None and stored.get("partition_key") != partition_key:
            return
        del self.items[item]

    def read_item(self, item, partition_key=None):
        # FIX (auditoría 2026-08-12): devolver la referencia interna (en vez
        # de una copia) permitía que dos "lecturas" distintas del mismo item
        # terminaran siendo el mismo objeto en memoria -- si el código bajo
        # test mutaba una, mutaba la otra en silencio, algo que Cosmos real
        # nunca haría (cada respuesta deserializa un dict nuevo). Eso rompía
        # justamente lo que los tests de concurrencia optimista (ETag) de
        # `_upsert_analysis` necesitan poder simular: dos lecturas
        # independientes que después divergen.
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        stored = self.items.get(item)
        if stored is None or (partition_key is not None and stored.get("partition_key") != partition_key):
            raise CosmosResourceNotFoundError(status_code=404, message="not found")
        return dict(stored)

    def query_items(self, query, parameters=None, enable_cross_partition_query=None, partition_key=None):
        param_map = {p["name"]: p["value"] for p in (parameters or [])}
        results = list(self.items.values())

        if partition_key is not None:
            results = [r for r in results if r.get("partition_key") == partition_key]

        type_match = re.search(r"c\.type\s*=\s*'(\w+)'", query)
        if type_match:
            results = [r for r in results if r.get("type") == type_match.group(1)]

        for field, param_name in re.findall(r"c\.(\w+)\s*=\s*(@\w+)", query):
            if param_name in param_map:
                value = param_map[param_name]
                results = [r for r in results if r.get(field) == value]

        for field, param_name in re.findall(r"c\.(\w+)\s*>=\s*(@\w+)", query):
            if param_name in param_map:
                value = param_map[param_name]
                results = [r for r in results if (r.get(field) or "") >= value]

        for field, param_name in re.findall(r"c\.(\w+)\s*<=\s*(@\w+)", query):
            if param_name in param_map:
                value = param_map[param_name]
                results = [r for r in results if (r.get(field) or "") <= value]

        if "NOT IS_DEFINED(c.deleted) OR c.deleted = false" in query:
            results = [r for r in results if not r.get("deleted")]

        if "ORDER BY c.uploaded_at ASC" in query:
            results.sort(key=lambda r: r.get("uploaded_at") or "")
        if "ORDER BY c.version_number DESC" in query:
            results.sort(key=lambda r: r.get("version_number") or 0, reverse=True)

        if query.strip().startswith("SELECT TOP 1"):
            results = results[:1]

        # Mismo motivo que en read_item: copias, no las referencias internas.
        return [dict(r) for r in results]


@pytest.fixture
def cosmos_only(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeCosmosContainer, str, str]:
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_only")
    get_settings.cache_clear()

    container = FakeCosmosContainer()
    monkeypatch.setattr(cosmos_runtime, "get_cosmos_container", lambda: container)
    monkeypatch.setattr(users_service, "get_cosmos_container", lambda: container)

    user_id = str(uuid4())
    container.add(
        {
            "id": f"user::{user_id}",
            "type": "user",
            "partition_key": f"user::{user_id}",
            "user_id": user_id,
            "email": "cosmos-user@cedia.com",
            "password_hash": get_password_hash("Test1234!"),
            "name": "Cosmos User",
            "deleted": False,
        }
    )
    token = create_access_token(user_id)

    yield container, user_id, token

    get_settings.cache_clear()
