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
        return iter(
            [
                {
                    "@search.score": 1.8,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 1,
                    "chunk_index": 0,
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
                        "@search.score": 1.0,
                        "analysis_id": "analysis-1",
                        "document_id": "doc-2",
                        "page_number": 2,
                        "chunk_index": 1,
                        "content": "Presupuesto oficial: AR$ 12.000.000",
                    }
                ]
            )
        return iter([])


def test_cloud_search_executes_once_and_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _FakeSearchClient()

    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(query="fecha de presentacion de ofertas", analysis_id="analysis-1", top_k=5)

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-1"
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["filter"] == "analysis_id eq 'analysis-1'"


def test_cloud_search_uses_wildcard_fallback_when_query_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _FakeWildcardSearchClient()
    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(query="monto estimado del contrato", analysis_id="analysis-1", top_k=5)

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-2"
    assert len(fake_client.calls) == 2
    assert fake_client.calls[1]["search_text"] == "*"


class _FakeRankingSearchClient:
    """Devuelve dos chunks con el score de relevancia hibrida que Azure ya
    calculo (`@search.score`) en orden ASCENDENTE en la respuesta cruda, para
    confirmar que el ranking final se basa en ese score real y no en el orden
    en que Azure los devolvio ni en un heuristico propio de seccion (bug real:
    antes se descartaba `@search.score` y se reordenaba solo con un bonus de
    seccion + overlap lexico)."""

    def search(self, **kwargs) -> Iterator[dict]:
        return iter(
            [
                {
                    "@search.score": 0.4,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-menos-relevante",
                    "page_number": 1,
                    "chunk_index": 0,
                    "content": "El monto de la garantia es variable",
                },
                {
                    "@search.score": 1.9,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-mas-relevante",
                    "page_number": 1,
                    "chunk_index": 1,
                    "content": "La garantia de mantenimiento de oferta",
                },
            ]
        )


def test_cloud_search_ranking_usa_el_score_hibrido_de_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _FakeRankingSearchClient())

    results = azure_search.search_hybrid(query="monto garantia", analysis_id="analysis-1", top_k=5)

    assert results[0]["document_id"] == "doc-mas-relevante"
    assert results[1]["document_id"] == "doc-menos-relevante"


class _FakeSchemaSearchClient:
    """Simula documents-index con el esquema de heading_path/heading_level
    (post rediseno markdown) y un chunk viejo indexado antes de esa migracion,
    donde esos campos existen en el esquema pero valen None."""

    def search(self, **kwargs) -> Iterator[dict]:
        return iter(
            [
                {
                    "@search.score": 1.5,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 3,
                    "chunk_index": 0,
                    "heading_path": ["Anexo I", "Planilla de Cantidades"],
                    "heading_level": 2,
                    "section_path": "Anexo I > Planilla de Cantidades",
                    "block_type": "table",
                    "table_ref": '{"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]}',
                    "content": "Tabla T1 | Fila 1 | Cantidad: 200",
                },
                {
                    "@search.score": 1.1,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-0",
                    "page_number": 1,
                    "chunk_index": 0,
                    "heading_path": None,
                    "heading_level": None,
                    "section_path": None,
                    "block_type": None,
                    "table_ref": None,
                    "content": "Contenido indexado antes de la migracion del esquema",
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
        lambda: ["analysis_id", "document_id", "heading_path", "heading_level", "section_path", "block_type", "table_ref", "content"],
    )

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _FakeSchemaSearchClient())

    results = azure_search.search_hybrid(query="cantidad", analysis_id="analysis-1", top_k=5)
    by_doc = {item["document_id"]: item for item in results}

    table_chunk = by_doc["doc-1"]
    assert table_chunk["block_type"] == "table"
    assert table_chunk["table_ref"] == {"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]}
    assert table_chunk["heading_path"] == ["Anexo I", "Planilla de Cantidades"]
    assert table_chunk["heading_level"] == 2
    assert table_chunk["section_path"] == "Anexo I > Planilla de Cantidades"

    # Chunk indexado antes de la migracion: los campos nuevos vienen en None desde
    # Azure (la clave existe en el esquema pero nunca se completo), y deben caer a
    # defaults seguros en vez de propagar None a los extractores.
    legacy_chunk = by_doc["doc-0"]
    assert legacy_chunk["block_type"] == "paragraph"
    assert legacy_chunk["table_ref"] is None
    assert legacy_chunk["heading_path"] == []
    assert legacy_chunk["heading_level"] == 0
    assert legacy_chunk["section_path"] == "general"
