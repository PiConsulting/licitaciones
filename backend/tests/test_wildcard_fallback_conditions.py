"""RET-02: el fallback wildcard estaba gobernado por una condición muerta.

`_search_azure` decidía si reintentar con `search_text="*"` mirando
`category_filter`, un parámetro que ningún llamador real pasaba desde el cambio
de arquitectura de 2026-08-12 (la categoría pasó a ser un boost de ranking, no
un filtro). Con `category_filter` siempre en None, la condición
`if not raw_results and not category_filter` era simplemente
`if not raw_results`: el wildcard se disparaba SIEMPRE que la búsqueda volvía
vacía -- justo el comportamiento que el comentario del código declaraba
peligroso.

Estos tests fijan las dos mitades del fix:

  1. el parámetro `category_filter` no existe más (y con él, el filtro OData
     por categoría que nunca se ejecutaba);
  2. el wildcard corre sólo cuando la búsqueda fue puramente léxica porque el
     embedding de la query falló. Si la mitad vectorial corrió, Azure devuelve
     los k vecinos más cercanos dentro del filtro sin umbral de similitud: un
     resultado vacío significa "no hay chunks de este análisis en el índice", y
     el wildcard tampoco encontraría nada.
"""

from __future__ import annotations

import inspect
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


class _EmptyThenWildcardClient:
    """Devuelve vacío para cualquier búsqueda salvo el wildcard."""

    def __init__(self) -> None:
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


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> _EmptyThenWildcardClient:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _EmptyThenWildcardClient()
    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["analysis_id", "document_id", "content"],
    )

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)
    return fake_client


# ---------------------------------------------------------------------------
# 1. El parámetro muerto ya no existe
# ---------------------------------------------------------------------------


def test_search_hybrid_ya_no_acepta_category_filter() -> None:
    """El filtro por categoría era código muerto: la firma lo ofrecía, el
    cuerpo construía el filtro OData, y ningún llamador real lo usaba."""
    assert "category_filter" not in inspect.signature(azure_search.search_hybrid).parameters
    assert "category_filter" not in inspect.signature(azure_search._search_azure).parameters


def test_el_filtro_odata_solo_acota_por_analysis_id(cliente) -> None:
    azure_search.search_hybrid(query="garantías exigidas", analysis_id="analysis-1", top_k=5)

    for call in cliente.calls:
        assert call["filter"] == "analysis_id eq 'analysis-1'"
        assert "primary_category" not in call["filter"]
        assert "secondary_categories" not in call["filter"]


# ---------------------------------------------------------------------------
# 2. La condición real del fallback
# ---------------------------------------------------------------------------


def test_con_vector_disponible_un_resultado_vacio_no_dispara_wildcard(
    cliente, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si la mitad vectorial corrió, vacío significa "no hay chunks indexados
    para este analysis_id" -- el wildcard devolvería vacío igual, y antes en
    cambio metía chunks arbitrarios de OTRO camino al prompt."""
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: [0.1] * 3072)

    results = azure_search.search_hybrid(
        query="causales de rechazo de la oferta", analysis_id="analysis-1", top_k=5
    )

    assert results == []
    assert len(cliente.calls) == 1, "no puede haber una segunda búsqueda con '*'"
    assert cliente.calls[0]["search_text"] != "*"


def test_sin_vector_el_wildcard_sigue_siendo_la_unica_salida(
    cliente, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modo degradado: si el embedding de la query falló, la búsqueda fue sólo
    BM25 y un cero puede ser un problema de matcheo léxico, no de indexación.
    Ahí el wildcard sí aporta."""
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: None)

    results = azure_search.search_hybrid(
        query="causales de rechazo de la oferta", analysis_id="analysis-1", top_k=5
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-2"
    assert len(cliente.calls) == 2
    assert cliente.calls[1]["search_text"] == "*"


def test_una_busqueda_con_resultados_nunca_reintenta(cliente, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarda de no-regresión: el fallback es para el caso vacío, no un
    segundo pase que amplíe el contexto."""
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: None)

    class _ConResultados(_EmptyThenWildcardClient):
        def search(self, **kwargs):
            self.calls.append(kwargs)
            return iter(
                [
                    {
                        "@search.score": 2.5,
                        "analysis_id": "analysis-1",
                        "document_id": "doc-1",
                        "page_number": 1,
                        "chunk_index": 0,
                        "content": "La garantía de mantenimiento de oferta será del 1%.",
                    }
                ]
            )

    con_resultados = _ConResultados()
    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: con_resultados)

    results = azure_search.search_hybrid(query="garantías", analysis_id="analysis-1", top_k=5)

    assert len(results) == 1
    assert len(con_resultados.calls) == 1


# ---------------------------------------------------------------------------
# 3. Los dos caminos vacíos se loguean como error, no como warning
# ---------------------------------------------------------------------------


def _capturar_logs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    capturados: list[tuple[str, dict]] = []

    class _Logger:
        def error(self, event, **kwargs):
            capturados.append((event, kwargs))

        def warning(self, event, **kwargs):
            capturados.append((event, kwargs))

        def info(self, event, **kwargs):
            capturados.append((event, kwargs))

        def debug(self, event, **kwargs):
            capturados.append((event, kwargs))

    monkeypatch.setattr(azure_search, "logger", _Logger())
    return capturados


def test_el_wildcard_se_loguea_como_error(cliente, monkeypatch: pytest.MonkeyPatch) -> None:
    """Era un warning. El contexto que llega al prompt no está ordenado por
    relevancia: eso amerita error, porque explica extracciones raras."""
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: None)
    capturados = _capturar_logs(monkeypatch)

    azure_search.search_hybrid(query="garantías", analysis_id="analysis-1", top_k=5)

    eventos = {evento for evento, _ in capturados}
    assert "azure_search_wildcard_fallback" in eventos


def test_analisis_sin_chunks_se_reporta_explicitamente(cliente, monkeypatch: pytest.MonkeyPatch) -> None:
    """Antes este caso quedaba enmascarado detrás del wildcard: el log decía
    "trying wildcard" y no que el análisis no estaba indexado."""
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: [0.1] * 3072)
    capturados = _capturar_logs(monkeypatch)

    azure_search.search_hybrid(query="garantías", analysis_id="analysis-1", top_k=5)

    eventos = {evento for evento, _ in capturados}
    assert "azure_search_analysis_sin_chunks" in eventos
    assert "azure_search_wildcard_fallback" not in eventos
