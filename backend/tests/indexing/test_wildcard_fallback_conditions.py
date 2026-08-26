"""RET-02: el fallback wildcard estaba gobernado por una condición muerta.

`_search_azure` decidía si reintentar con `search_text="*"` mirando
`category_filter`, un parámetro que ningún llamador real pasaba desde el cambio
de arquitectura de 2026-08-12 (la categoría pasó a ser un boost de ranking, no
un filtro). Con `category_filter` siempre en None, la condición
`if not raw_results and not category_filter` era simplemente
`if not raw_results`: el wildcard se disparaba SIEMPRE que la búsqueda volvía
vacía -- justo el comportamiento que el comentario del código declaraba
peligroso.

Este archivo originalmente fijaba las dos mitades de ese fix intermedio (RET-02):

  1. el parámetro `category_filter` no existe más (y con él, el filtro OData
     por categoría que nunca se ejecutaba);
  2. el wildcard corre sólo cuando la búsqueda fue puramente léxica porque el
     embedding de la query falló.

STORY 10.3 (posterior) eliminó el wildcard fallback por completo: ambos casos
vacíos ahora elevan `RuntimeError` en vez de reintentar con `"*"`. Los tests
que verificaban el comportamiento del punto 2 (el wildcard corriendo) y su
logging quedaron obsoletos -- están cubiertos por
`test_wildcard_fallback_removed.py`, que valida el reemplazo (RuntimeError,
sin reintento). Se conservan acá solo los dos tests del punto 1, que siguen
vigentes: no son sobre el wildcard sino sobre la firma de `search_hybrid` y el
filtro OData.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator

import pytest

from infra.config import get_settings
from infra.ports import azure_search


def _set_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "false")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "fake")
    monkeypatch.setenv("AZURE_SEARCH_INDEX_NAME", "documents-index")


class _ResultadosSiempreClient:
    """Devuelve resultados no vacíos para cualquier búsqueda -- a diferencia
    del wildcard fallback (eliminado en Story 10.3), acá no hace falta un
    camino "vacío" para probar el filtro OData."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> Iterator[dict]:
        self.calls.append(kwargs)
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


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> _ResultadosSiempreClient:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    fake_client = _ResultadosSiempreClient()
    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["analysis_id", "document_id", "content"],
    )
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda *_args, **_kwargs: [0.1] * 3072)

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)
    return fake_client


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
