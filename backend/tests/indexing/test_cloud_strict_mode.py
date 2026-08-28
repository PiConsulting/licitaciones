from __future__ import annotations

import pytest

from infra.config import get_settings


def _set_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")


def test_cloud_config_reports_missing_required_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "")
    get_settings.cache_clear()

    settings = get_settings()
    missing = settings.missing_cloud_required_variables()

    assert "AZURE_BLOB_CONNECTION_STRING" in missing
    assert "AZURE_BLOB_CONTAINER_NAME" in missing
    assert "AZURE_OPENAI_DEPLOYMENT" in missing
    assert "AZURE_OPENAI_EMBEDDING_DEPLOYMENT" in missing


def test_health_cloud_reports_missing_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "")
    get_settings.cache_clear()

    from main import _azure_config_health

    status, _, missing = _azure_config_health()

    assert status == "error"
    assert "AZURE_BLOB_CONNECTION_STRING" in missing
    assert "AZURE_BLOB_CONTAINER_NAME" in missing


def test_blob_builder_fails_without_config_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "")
    get_settings.cache_clear()

    from analysis.service import _build_blob_storage

    with pytest.raises(RuntimeError, match="AZURE_BLOB_CONNECTION_STRING"):
        _build_blob_storage()


def test_embedding_adapter_requires_cloud_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
    get_settings.cache_clear()

    from indexing.embeddings import _build_adapter

    with pytest.raises(RuntimeError, match="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"):
        _build_adapter()


def test_chat_client_requires_cloud_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "")
    get_settings.cache_clear()

    from infra.adapters.azure_openai import get_azure_openai_client

    with pytest.raises(RuntimeError, match="AZURE_OPENAI_DEPLOYMENT"):
        get_azure_openai_client()


def test_run_health_checks_no_longer_has_cosmos_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Historia 22.10: eliminado el chequeo de Cosmos por completo -- el
    payload de /health no debe tener la clave 'cosmos'."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    get_settings.cache_clear()

    import main as main_module

    _status_code, payload = main_module._run_health_checks()

    assert "cosmos" not in payload["checks"]
    assert not hasattr(main_module, "_cosmos_health")


def test_missing_cloud_required_variables_has_no_cosmos_or_persistence_mode_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4: sin PERSISTENCE_MODE/COSMOS_* en el set de variables requeridas."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()

    settings = get_settings()
    required_keys = set(settings.cloud_required_variables().keys())

    assert not any(key.startswith("COSMOS_") for key in required_keys)
    assert "PERSISTENCE_MODE" not in required_keys
