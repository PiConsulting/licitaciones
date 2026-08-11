from __future__ import annotations

import pytest

from shared.config import get_settings


def _set_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")


def test_cloud_config_reports_missing_required_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "")
    monkeypatch.setenv("COSMOS_ENDPOINT", "")
    monkeypatch.setenv("COSMOS_KEY", "")
    monkeypatch.setenv("COSMOS_DATABASE", "")
    monkeypatch.setenv("COSMOS_CONTAINER", "")
    get_settings.cache_clear()

    settings = get_settings()
    missing = settings.missing_cloud_required_variables()

    assert "AZURE_BLOB_CONNECTION_STRING" in missing
    assert "AZURE_BLOB_CONTAINER_NAME" in missing
    assert "AZURE_OPENAI_DEPLOYMENT" in missing
    assert "AZURE_OPENAI_EMBEDDING_DEPLOYMENT" in missing
    assert "COSMOS_ENDPOINT" in missing
    assert "COSMOS_CONTAINER" in missing


def test_health_cloud_reports_missing_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "dual_write")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "")
    monkeypatch.setenv("COSMOS_ENDPOINT", "")
    monkeypatch.setenv("COSMOS_KEY", "")
    monkeypatch.setenv("COSMOS_DATABASE", "")
    monkeypatch.setenv("COSMOS_CONTAINER", "")
    get_settings.cache_clear()

    from main import _azure_config_health

    status, _, missing = _azure_config_health()

    assert status == "error"
    assert "AZURE_BLOB_CONNECTION_STRING" in missing
    assert "AZURE_BLOB_CONTAINER_NAME" in missing
    assert "COSMOS_ENDPOINT" in missing


def test_cloud_config_rejects_localhost_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/licitaciones")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "blob")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "pliegos")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "emb")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    get_settings.cache_clear()

    settings = get_settings()
    with pytest.raises(RuntimeError, match="DATABASE_URL no puede apuntar a localhost"):
        settings.validate_cloud_configuration()


def test_cosmos_temporal_allows_localhost_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/licitaciones")
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_temporal")
    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "blob")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "pliegos")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "emb")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://example.documents.azure.com")
    monkeypatch.setenv("COSMOS_KEY", "fake")
    monkeypatch.setenv("COSMOS_DATABASE", "pliegos")
    monkeypatch.setenv("COSMOS_CONTAINER", "container_pliegos")
    get_settings.cache_clear()

    settings = get_settings()
    settings.validate_cloud_configuration()


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

    from extraction.embeddings import _build_adapter

    with pytest.raises(RuntimeError, match="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"):
        _build_adapter()


def test_chat_client_requires_cloud_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "")
    get_settings.cache_clear()

    from shared.ports.azure_openai import get_azure_openai_client

    with pytest.raises(RuntimeError, match="AZURE_OPENAI_DEPLOYMENT"):
        get_azure_openai_client()


def test_search_index_contract_validator_detects_invalid_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")
    monkeypatch.setenv("AZURE_SEARCH_EMBEDDING_DIMENSIONS", "3072")
    get_settings.cache_clear()

    class _Field:
        def __init__(self, name: str, *, filterable: bool = False, vector_search_dimensions: int | None = None) -> None:
            self.name = name
            self.filterable = filterable
            self.vector_search_dimensions = vector_search_dimensions

    class _Index:
        def __init__(self) -> None:
            self.fields = [
                _Field("id"),
                _Field("analysis_id", filterable=True),
                _Field("content"),
                _Field("document_id"),
                _Field("page_number"),
                _Field("chunk_index"),
                _Field("embedding", vector_search_dimensions=1536),
            ]

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_index(self, _name: str) -> _Index:
            return _Index()

    from extraction import ai_search

    monkeypatch.setattr(ai_search, "SearchIndexClient", _Client)

    with pytest.raises(RuntimeError, match="embedding"):
        ai_search.validate_index_contract()
