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


class _FakeSchemaMigrationSearchClient:
    """Simula documents-index tras agregarle section_path/section_level/block_type/table_ref.

    Devuelve un chunk de tabla ya subido con el esquema nuevo y un chunk viejo,
    indexado antes de la migracion, donde esos campos existen en el esquema pero
    valen None (Azure Search los completa asi para documentos preexistentes).
    """

    def search(self, **kwargs) -> Iterator[dict]:
        return iter(
            [
                {
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 3,
                    "chunk_index": 0,
                    "section_key": "anexos",
                    "section_path": "Anexo I",
                    "section_level": 1,
                    "block_type": "table",
                    "table_ref": '{"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]}',
                    "content": "Tabla T1 | Fila 1 | Cantidad: 200",
                },
                {
                    "analysis_id": "analysis-1",
                    "document_id": "doc-0",
                    "page_number": 1,
                    "chunk_index": 0,
                    "section_key": "articulos",
                    "section_path": None,
                    "section_level": None,
                    "block_type": None,
                    "table_ref": None,
                    "content": "Articulo indexado antes de la migracion del esquema",
                },
            ]
        )


def test_cloud_search_deserializes_table_ref_and_defaults_legacy_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["analysis_id", "document_id", "section_key", "section_path", "section_level", "block_type", "table_ref", "content"],
    )

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _FakeSchemaMigrationSearchClient())

    results = azure_search.search_hybrid(query="cantidad", analysis_id="analysis-1", top_k=5, section_key="anexos_obligatorios")
    by_doc = {item["document_id"]: item for item in results}

    table_chunk = by_doc["doc-1"]
    assert table_chunk["block_type"] == "table"
    assert table_chunk["table_ref"] == {"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]}
    assert table_chunk["section_path"] == "Anexo I"
    assert table_chunk["section_level"] == 1

    # Chunk indexado antes de la migracion: los campos nuevos vienen en None desde
    # Azure (la clave existe en el esquema pero nunca se completo), y deben caer a
    # los mismos defaults que antes de que el esquema tuviera estos campos.
    legacy_chunk = by_doc["doc-0"]
    assert legacy_chunk["block_type"] == "paragraph"
    assert legacy_chunk["table_ref"] is None
    assert legacy_chunk["section_path"] == "articulos"
    assert legacy_chunk["section_level"] == 0
