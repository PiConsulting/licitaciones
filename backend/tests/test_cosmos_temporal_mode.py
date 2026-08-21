from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analysis import metadata_persistence
from analysis.models import Analysis
from shared.config import get_settings
from shared.database import SessionLocal
from users.models import User


def _set_cloud_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "blob")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "pliegos")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://di.example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://openai.example.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "emb")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://cosmos.example.documents.azure.com")
    monkeypatch.setenv("COSMOS_KEY", "fake")
    monkeypatch.setenv("COSMOS_DATABASE", "pliegos")
    monkeypatch.setenv("COSMOS_CONTAINER", "container_pliegos")


def test_validate_cloud_configuration_allows_cosmos_temporal_with_localhost_db(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_cloud_minimum(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_temporal")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/licitaciones")
    get_settings.cache_clear()

    settings = get_settings()
    settings.validate_cloud_configuration()


def test_health_skips_database_check_in_cosmos_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_cloud_minimum(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_temporal")
    get_settings.cache_clear()

    # FIX (auditoría 2026-08-12, flujo Cosmos, hallazgo #5): este test seguía
    # apuntando a un endpoint de Cosmos que no existe de verdad
    # (COSMOS_ENDPOINT="https://cosmos.example.documents.azure.com" seteado
    # arriba en `_set_cloud_minimum`, solo para satisfacer
    # `validate_cloud_configuration()`). Antes del fix de este mismo hallazgo,
    # `/health` nunca intentaba una conexión real a Cosmos, así que ese
    # endpoint falso nunca se usaba de verdad y el test pasaba por accidente.
    # Ahora que `_cosmos_health()` sí hace un `container.read()` real en todo
    # modo que usa Cosmos (justamente lo que este hallazgo pedía), hay que
    # mockear el container -- si no, este test intenta una conexión de red
    # real contra un dominio inexistente y el chequeo de Cosmos legítimamente
    # reporta "error" (que es el comportamiento correcto para un endpoint que
    # no responde, no un bug nuevo).
    fake_container = type("FakeContainer", (), {"read": lambda self: {"id": "container-1"}})()
    monkeypatch.setattr("shared.cosmos_container.get_cosmos_container", lambda: fake_container)

    import main

    status_code, payload = main._run_health_checks()

    assert status_code == 200
    assert payload["checks"]["database"]["status"] == "skipped"
    assert payload["checks"]["cosmos"]["status"] == "ok"
    # FIX (auditoría 2026-08-12): mismo motivo que en test_health.py --
    # "production" ya no es un valor posible, `main.py` hardcodea "cloud".
    assert payload["checks"]["adapters"]["mode"] == "cloud"


def test_cosmos_metadata_sink_upserts_with_analysis_partition_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response(dict):
        def get_response_headers(self):
            return {"x-ms-request-charge": "3.14"}

    class _Container:
        def __init__(self) -> None:
            self.upserts: list[dict] = []

        def upsert_item(self, item):
            self.upserts.append(item)
            return _Response()

    container = _Container()

    sink = metadata_persistence.CosmosMetadataSink(
        endpoint="https://cosmos.example.documents.azure.com",
        key="fake",
        database="pliegos",
        container="container_pliegos",
    )
    monkeypatch.setattr(sink, "_get_container_client", lambda: container)

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    analysis = Analysis(
        created_by=user.id,
        status="queued",
        current_stage="queued",
        progress_percentage=0,
        correlation_id="corr-1",
        extraction_metadata={"stage_progress": "En cola"},
        updated_at=datetime.now(UTC),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    sink.persist(analysis=analysis, documents=[], versions=[], event="analysis_queued")

    assert container.upserts
    first_item = container.upserts[0]
    assert first_item["analysis_id"] == analysis.id
    assert first_item["partition_key"] == analysis.id
    db.close()


def test_status_endpoint_prefers_cosmos_runtime_in_cosmos_temporal(
    client,
    auth_token,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_cloud_minimum(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_temporal")
    get_settings.cache_clear()

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="queued",
        progress_percentage=0,
        correlation_id="corr-2",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    db.close()

    import analysis.routes as analysis_routes

    monkeypatch.setattr(
        analysis_routes,
        "read_runtime_analysis_from_cosmos",
        lambda _analysis_id: {
            "id": analysis.id,
            "status": "analyzed",
            "current_stage": "completed",
            "progress_percentage": 100,
            "stage_progress": "Analizado",
            "started_at": None,
            "timeout_at": None,
            "timeout_warning_at": None,
            "error_message": None,
            "extracted_data": {"plazos": {}},
            "conflicts": [],
        },
    )

    response = client.get(
        f"/api/v1/analyses/{analysis.id}/status",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "analyzed"
    assert payload["current_stage"] == "completed"
    assert payload["progress_percentage"] == 100
