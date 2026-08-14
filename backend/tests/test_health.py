from shared.config import get_settings


def test_health_ready_returns_checks(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    # FIX (auditoría 2026-08-12): "development" es un valor que ya no existe
    # -- `main.py` (ver comentario "eliminados adaptadores locales") hardcodea
    # `mode` a "cloud" desde que se sacaron los adaptadores locales. Esta
    # aserción quedó desactualizada de ese refactor.
    assert payload["checks"]["adapters"]["mode"] == "cloud"


def test_health_degraded_when_database_unavailable(client, monkeypatch):
    monkeypatch.setattr("main._database_health", lambda: ("error", "No se pudo conectar a la base de datos"))

    response = client.get("/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "error"


def test_azure_config_reports_missing_variables(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")

    from main import _azure_config_health

    status, message, missing = _azure_config_health()

    assert status == "error"
    assert message == "Falta configuración para Azure"
    assert "AZURE_BLOB_CONNECTION_STRING" in missing
    assert "AZURE_OPENAI_API_KEY" in missing

    get_settings.cache_clear()
