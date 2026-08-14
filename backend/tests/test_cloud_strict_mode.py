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
                _Field("primary_category"),
                _Field("secondary_categories"),
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


def test_search_index_contract_validator_detects_missing_category_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX (US-4.2): repetir el incidente historico donde primary_category y
    secondary_categories no estaban en el indice real -- antes esto pasaba
    inadvertido hasta el primer upload_chunks() en produccion. Ahora tiene
    que fallar el chequeo de arranque con un mensaje explicito."""
    _set_production_env(monkeypatch)
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")
    monkeypatch.setenv("AZURE_SEARCH_EMBEDDING_DIMENSIONS", "1536")
    get_settings.cache_clear()

    class _Field:
        def __init__(self, name: str, *, filterable: bool = False, vector_search_dimensions: int | None = None) -> None:
            self.name = name
            self.filterable = filterable
            self.vector_search_dimensions = vector_search_dimensions

    class _Index:
        def __init__(self) -> None:
            # Deliberadamente SIN primary_category/secondary_categories,
            # replicando el schema desactualizado del incidente historico.
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
    ai_search._validate_index_contract_cached.cache_clear()

    with pytest.raises(RuntimeError, match="primary_category"):
        ai_search.validate_index_contract()


def test_to_index_document_logs_discarded_fields(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """FIX (US-4.2): antes _to_index_document descartaba en silencio campos
    que el indice real no declaraba. Si el schema de Azure queda desactualizado
    respecto al codigo, esto ahora debe quedar visible en los logs."""
    import structlog

    from extraction.ai_search import AzureSearchAdapter

    adapter = AzureSearchAdapter(endpoint="https://fake", key="fake", index_name="fake-index")
    adapter._cached_index_fields = {"id", "analysis_id", "content"}

    events: list[dict] = []

    def _capture(_logger: object, _method_name: str, event_dict: dict) -> dict:
        events.append(event_dict)
        raise structlog.DropEvent

    structlog.configure(
        processors=[_capture],
        wrapper_class=structlog.make_filtering_bound_logger(0),
    )
    try:
        result = adapter._to_index_document(
            {"id": "1", "analysis_id": "a", "content": "texto", "primary_category": "garantias"}
        )
    finally:
        structlog.reset_defaults()

    assert result == {"id": "1", "analysis_id": "a", "content": "texto"}
    discard_events = [e for e in events if e.get("event") == "search_index_document_fields_discarded"]
    assert discard_events, "se esperaba un warning por los campos descartados"
    assert discard_events[0]["discarded_fields"] == ["primary_category"]


def test_to_index_document_no_warning_when_all_fields_known() -> None:
    """No debe loguear nada si todos los campos del documento estan en el
    schema real del indice -- el warning es solo para drift, no ruido constante."""
    import structlog

    from extraction.ai_search import AzureSearchAdapter

    adapter = AzureSearchAdapter(endpoint="https://fake", key="fake", index_name="fake-index")
    adapter._cached_index_fields = {"id", "analysis_id", "content"}

    events: list[dict] = []

    def _capture(_logger: object, _method_name: str, event_dict: dict) -> dict:
        events.append(event_dict)
        raise structlog.DropEvent

    structlog.configure(
        processors=[_capture],
        wrapper_class=structlog.make_filtering_bound_logger(0),
    )
    try:
        adapter._to_index_document({"id": "1", "analysis_id": "a", "content": "texto"})
    finally:
        structlog.reset_defaults()

    discard_events = [e for e in events if e.get("event") == "search_index_document_fields_discarded"]
    assert not discard_events


def test_startup_validates_index_contract_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """FIX (US-4.2): antes validate_index_contract() recien se disparaba en el
    primer upload_chunks() real, en medio de un analisis ya en curso. Tiene
    que dispararse en el startup real de la app, junto con
    validate_cloud_configuration(), para fallar temprano si el schema del
    indice de Azure quedo desactualizado."""
    _set_production_env(monkeypatch)
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_temporal")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/licitaciones")
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

    import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "validate_index_contract", lambda: calls.append("validated"))

    app = main_module.create_app()
    assert app.router.on_startup, "se esperaba al menos un handler de startup"
    for handler in app.router.on_startup:
        handler()

    assert calls == ["validated"], "validate_index_contract() debe llamarse desde el startup real de la app"


def test_startup_skips_index_contract_check_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuera de produccion (dev local sin Azure real configurado) el chequeo
    de schema del indice no debe dispararse -- rompería el arranque local."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    get_settings.cache_clear()

    import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "validate_index_contract", lambda: calls.append("validated"))

    app = main_module.create_app()
    for handler in app.router.on_startup:
        handler()

    assert calls == [], "validate_index_contract() no debe llamarse fuera de produccion"


def test_cosmos_health_ok_cuando_container_responde(monkeypatch: pytest.MonkeyPatch) -> None:
    """FIX (auditoría 2026-08-12, flujo Cosmos): antes no había NINGÚN
    chequeo real de conectividad a Cosmos -- solo se validaba que las
    variables de entorno estuvieran seteadas."""
    import main as main_module

    fake_container = type("FakeContainer", (), {"read": lambda self: {"id": "container-1"}})()
    monkeypatch.setattr("shared.cosmos_container.get_cosmos_container", lambda: fake_container)

    status, message = main_module._cosmos_health()

    assert status == "ok"
    assert "operativa" in message


def test_cosmos_health_error_cuando_container_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un outage o error de red real contra Cosmos tiene que marcar 'error',
    no pasar desapercibido."""
    import main as main_module

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated Cosmos outage")

    fake_container = type("FakeContainer", (), {"read": _raise})()
    monkeypatch.setattr("shared.cosmos_container.get_cosmos_container", lambda: fake_container)

    status, message = main_module._cosmos_health()

    assert status == "error"
    assert "Cosmos" in message


def test_run_health_checks_saltea_cosmos_en_modo_sql_puro(monkeypatch: pytest.MonkeyPatch) -> None:
    """En modo 'sql' puro, Cosmos no se usa -- el chequeo debe ser 'skipped',
    no intentar conectar (y mucho menos fallar por eso)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("PERSISTENCE_MODE", "sql")
    get_settings.cache_clear()

    import main as main_module

    def _fail_if_called():
        raise AssertionError("no deberia intentar conectar a Cosmos en modo sql puro")

    monkeypatch.setattr(main_module, "_cosmos_health", _fail_if_called)

    _status_code, payload = main_module._run_health_checks()

    assert payload["checks"]["cosmos"]["status"] == "skipped"


def test_run_health_checks_corre_cosmos_health_en_modo_cosmos_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """En cualquier modo que use Cosmos (cosmos/dual_write/cosmos_temporal/
    cosmos_only), el chequeo real de Cosmos tiene que correr -- antes nunca
    corría, ni siquiera en cosmos_only donde Cosmos es la única fuente de
    verdad."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("PERSISTENCE_MODE", "cosmos_only")
    get_settings.cache_clear()

    import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "_cosmos_health", lambda: (calls.append("called"), ("error", "no disponible"))[1])

    _status_code, payload = main_module._run_health_checks()

    assert calls == ["called"]
    assert payload["checks"]["cosmos"]["status"] == "error"
    assert payload["status"] == "degraded"
