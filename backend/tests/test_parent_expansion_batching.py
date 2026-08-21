"""RET-03: la expansión children→parent hacía una llamada HTTP por child.

`_expand_children_to_parents` resolvía cada parent con
`client.get_document(key=parent_id)` DENTRO del loop -- una llamada sincrónica
por cada child de la ventana de expansión. Para `garantias` (top_k=35 en el
glossary) la ventana llega a 70 chunks, y el grafo corre las 8 categorías en
paralelo.

El costo escala con cuántos artículos con incisos tiene el pliego, no con su
largo. Como `calculate_timeout_minutes` dimensiona el timeout por cantidad de
páginas, un pliego bien estructurado -- justo donde parent/child aporta -- podía
vencer por timeout mientras uno plano del mismo largo no.

Además se pedían `top_k * 3` documentos a Azure cuando la ventana de expansión
corta en `top_k * 2`: el último tercio se traía con su `content` completo para
descartarlo sin mirarlo.
"""

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


def _child(index: int, parent_index: int) -> dict:
    return {
        "@search.score": 10.0 - index * 0.01,
        "id": f"analysis-1--doc-1--{index}",
        "analysis_id": "analysis-1",
        "document_id": "doc-1",
        "page_number": 1 + index // 10,
        "chunk_index": index,
        "content": f"inciso {index}",
        "chunk_type": "child",
        "parent_chunk_id": f"analysis-1--doc-1--{parent_index}",
        "child_chunk_ids": [],
    }


def _parent(parent_index: int) -> dict:
    return {
        "id": f"analysis-1--doc-1--{parent_index}",
        "analysis_id": "analysis-1",
        "document_id": "doc-1",
        "page_number": 1,
        "chunk_index": parent_index,
        "content": f"Artículo {parent_index} completo con todos sus incisos",
        "chunk_type": "parent",
        "parent_chunk_id": None,
        "child_chunk_ids": [],
    }


class _ContadorDeLlamadas:
    """Un child por parent distinto: el peor caso para el patrón viejo."""

    def __init__(self, cantidad_de_parents: int) -> None:
        self.cantidad = cantidad_de_parents
        self.parents = {
            _parent(1000 + i)["id"]: _parent(1000 + i) for i in range(cantidad_de_parents)
        }
        self.busquedas_principales = 0
        self.busquedas_de_parents = 0
        self.tops_pedidos: list[int] = []
        self.get_document_calls = 0

    def search(self, **kwargs) -> Iterator[dict]:
        filter_expr = str(kwargs.get("filter") or "")
        if filter_expr.startswith("search.in(id"):
            self.busquedas_de_parents += 1
            pedidos = filter_expr.split("'")[1].split("|")
            return iter([self.parents[key] for key in pedidos if key in self.parents])

        self.busquedas_principales += 1
        self.tops_pedidos.append(int(kwargs.get("top") or 0))
        return iter([_child(i, 1000 + i) for i in range(self.cantidad)])

    def get_document(self, key: str) -> dict:  # pragma: no cover
        self.get_document_calls += 1
        raise AssertionError("RET-03: no puede haber una llamada por child")


@pytest.fixture
def entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()
    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["id", "analysis_id", "document_id", "content", "chunk_type", "parent_chunk_id"],
    )
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: None)


def _instalar(client, monkeypatch: pytest.MonkeyPatch) -> None:
    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: client)


# ---------------------------------------------------------------------------
# 1. La cantidad de llamadas deja de escalar con la cantidad de children
# ---------------------------------------------------------------------------


def test_setenta_children_de_parents_distintos_se_resuelven_en_una_llamada(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso que motiva el hallazgo: 70 children, 70 parents distintos.
    Antes eran 70 `get_document()` secuenciales."""
    client = _ContadorDeLlamadas(70)
    _instalar(client, monkeypatch)

    results = azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=35)

    assert client.get_document_calls == 0
    assert client.busquedas_de_parents == 1
    assert len(results) == 35
    assert all(chunk["chunk_type"] == "parent" for chunk in results)


def test_el_lote_se_parte_pero_no_una_llamada_por_child(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con más ids que el tamaño de lote, se parte en vueltas -- pero el
    divisor es el lote, no la cantidad de children."""
    client = _ContadorDeLlamadas(250)
    _instalar(client, monkeypatch)

    azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=125)

    esperado = -(-250 // azure_search._PARENT_LOOKUP_BATCH_SIZE)  # techo de la división
    assert client.busquedas_de_parents == esperado
    assert esperado < 250


def test_cada_parent_se_pide_una_sola_vez(entorno, monkeypatch: pytest.MonkeyPatch) -> None:
    """Varios children del mismo artículo comparten parent: el id no puede
    repetirse en el filtro."""

    class _MismoParent(_ContadorDeLlamadas):
        def search(self, **kwargs) -> Iterator[dict]:
            filter_expr = str(kwargs.get("filter") or "")
            if filter_expr.startswith("search.in(id"):
                self.busquedas_de_parents += 1
                self.ultimo_filtro = filter_expr
                return iter([_parent(1000)])
            return iter([_child(i, 1000) for i in range(8)])

    client = _MismoParent(1)
    client.parents = {_parent(1000)["id"]: _parent(1000)}
    _instalar(client, monkeypatch)

    results = azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=10)

    assert client.busquedas_de_parents == 1
    assert client.ultimo_filtro.count("analysis-1--doc-1--1000") == 1
    assert len(results) == 1


# ---------------------------------------------------------------------------
# 2. Degradación: un lote que falla no puede tumbar la búsqueda
# ---------------------------------------------------------------------------


def test_si_falla_el_lote_se_conservan_los_children(entorno, monkeypatch: pytest.MonkeyPatch) -> None:
    class _LoteRoto(_ContadorDeLlamadas):
        def search(self, **kwargs) -> Iterator[dict]:
            filter_expr = str(kwargs.get("filter") or "")
            if filter_expr.startswith("search.in(id"):
                self.busquedas_de_parents += 1
                raise RuntimeError("Azure caído")
            return iter([_child(i, 1000 + i) for i in range(3)])

    client = _LoteRoto(3)
    _instalar(client, monkeypatch)

    results = azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=10)

    assert len(results) == 3
    assert all(chunk["chunk_type"] == "child" for chunk in results)


def test_un_parent_borrado_no_pierde_el_child(entorno, monkeypatch: pytest.MonkeyPatch) -> None:
    class _ParentFaltante(_ContadorDeLlamadas):
        def search(self, **kwargs) -> Iterator[dict]:
            filter_expr = str(kwargs.get("filter") or "")
            if filter_expr.startswith("search.in(id"):
                self.busquedas_de_parents += 1
                return iter([])  # el parent ya no está en el índice
            return iter([_child(0, 1000)])

    client = _ParentFaltante(1)
    _instalar(client, monkeypatch)

    results = azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=10)

    assert len(results) == 1
    assert results[0]["chunk_type"] == "child"


# ---------------------------------------------------------------------------
# 3. La amplificación de la búsqueda principal
# ---------------------------------------------------------------------------


def test_no_se_piden_documentos_que_la_ventana_de_expansion_descarta(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se pedían `top_k * 3` pero la ventana corta en `top_k * 2`: el último
    tercio venía con su `content` completo para tirarse."""
    client = _ContadorDeLlamadas(1)
    _instalar(client, monkeypatch)

    azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=35)

    assert client.tops_pedidos == [70]
    assert 70 == max(35 * 2, 30)


def test_se_conserva_el_piso_de_treinta_para_top_k_chico(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Para categorías con top_k chico el piso de 30 sigue dando margen al
    dedupe children->parent."""
    client = _ContadorDeLlamadas(1)
    _instalar(client, monkeypatch)

    azure_search.search_hybrid(query="incisos", analysis_id="analysis-1", top_k=5)

    assert client.tops_pedidos == [30]
