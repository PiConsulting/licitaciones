from __future__ import annotations

from collections.abc import Iterator

import pytest

from shared.config import get_settings
from shared.ports import azure_search


def _set_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")


class _FakeSearchClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> Iterator[dict]:
        self.calls.append(kwargs)
        if "section_key eq" in kwargs.get("filter", ""):
            return iter([])
        return iter(
            [
                {
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 1,
                    "chunk_index": 0,
                    "section_key": "plazos",
                    "content": "Presentacion de ofertas: 15/09/2026 10:00 hs",
                }
            ]
        )


class _FakeWildcardSearchClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> Iterator[dict]:
        self.calls.append(kwargs)
        if kwargs.get("search_text") == "*":
            return iter(
                [
                    {
                        "analysis_id": "analysis-1",
                        "document_id": "doc-2",
                        "page_number": 2,
                        "chunk_index": 1,
                        "section_key": "general",
                        "content": "Presupuesto oficial: AR$ 12.000.000",
                    }
                ]
            )
        return iter([])


def test_cloud_search_falls_back_without_section_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _FakeSearchClient()

    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "section_key", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(
        query="fecha de presentacion de ofertas",
        analysis_id="analysis-1",
        top_k=5,
        section_key="plazos",
    )

    assert len(results) == 1
    assert results[0]["section_path"] == "plazos"
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["filter"] == "analysis_id eq 'analysis-1'"


def test_cloud_search_without_section_filter_executes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _FakeSearchClient()
    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "section_key", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(
        query="mantenimiento de oferta",
        analysis_id="analysis-1",
        top_k=5,
        section_key=None,
    )

    assert len(results) == 1
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["filter"] == "analysis_id eq 'analysis-1'"


def test_cloud_search_uses_wildcard_fallback_when_query_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _FakeWildcardSearchClient()
    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "section_key", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(
        query="monto estimado del contrato",
        analysis_id="analysis-1",
        top_k=5,
        section_key="estimacion_presupuesto",
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-2"
    assert len(fake_client.calls) == 2
    assert fake_client.calls[1]["search_text"] == "*"
