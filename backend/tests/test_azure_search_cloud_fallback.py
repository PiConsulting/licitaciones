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

    # FIX (auditoría 2026-08-13, hallazgo RET-02): el wildcard ahora corre sólo
    # en modo degradado (sin vector). Este test pasaba "de casualidad" porque en
    # el entorno de tests no hay Azure OpenAI y `_embed_query_or_none` devolvía
    # None por excepción; se explicita la precondición para que el test siga
    # verificando lo que dice verificar aunque eso cambie.
    monkeypatch.setattr(azure_search, "_embed_query_or_none", lambda _query: None)

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


class _FakeSourceFieldSearchClient:
    """Simula un indice ya migrado con el campo 'source' (RAG PHASE 3), mas un
    chunk indexado antes de esa migracion sin el campo."""

    def search(self, **kwargs) -> Iterator[dict]:
        return iter(
            [
                {
                    "@search.score": 1.2,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-nuevo",
                    "page_number": 5,
                    "chunk_index": 0,
                    "source": (
                        '{"page": 5, "block_type": "paragraph", '
                        '"blocks": [{"block_id": "para_3", '
                        '"bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 12.0}, '
                        '"text": "La garantia sera del 1%"}]}'
                    ),
                    "content": "La garantia sera del 1%",
                },
                {
                    "@search.score": 0.9,
                    "analysis_id": "analysis-1",
                    "document_id": "doc-viejo",
                    "page_number": 1,
                    "chunk_index": 0,
                    "source": None,
                    "content": "Contenido indexado antes de agregar 'source'",
                },
            ]
        )


def test_cloud_search_deserializes_source_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """US-4.1 (hallazgo relacionado a H-3/seccion 9): 'source' es el campo
    estructurado que highlight.py y _augment_identificacion_payload prefieren
    sobre 'blocks', pero como no se pedia en el SELECT nunca llegaba -- ambos
    consumidores caian siempre al fallback legacy aunque el indice ya lo
    tuviera poblado."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["analysis_id", "document_id", "page_number", "chunk_index", "source", "content"],
    )

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _FakeSourceFieldSearchClient())

    results = azure_search.search_hybrid(query="garantia", analysis_id="analysis-1", top_k=5)
    by_doc = {item["document_id"]: item for item in results}

    nuevo = by_doc["doc-nuevo"]
    assert nuevo["source"] == {
        "page": 5,
        "block_type": "paragraph",
        "blocks": [
            {
                "block_id": "para_3",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 12.0},
                "text": "La garantia sera del 1%",
            }
        ],
    }

    # Chunk indexado antes de que existiera 'source': debe caer a None, no
    # romper -- highlight.py y base.py ya saben caer al fallback legacy
    # cuando 'source' es None/falsy.
    viejo = by_doc["doc-viejo"]
    assert viejo["source"] is None


def test_cloud_search_returns_real_search_score_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """US-2.2 (hallazgo M-2): el score real de relevancia hibrida de Azure
    tiene que quedar accesible en el chunk devuelto (antes se calculaba y se
    descartaba), para que el boost por categoria de
    _retrieve_with_category_priority no tenga que aproximarlo por rank."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "content"])

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _FakeRankingSearchClient())

    results = azure_search.search_hybrid(query="monto garantia", analysis_id="analysis-1", top_k=5)

    scores_by_doc = {item["document_id"]: item["search_score"] for item in results}
    assert scores_by_doc["doc-mas-relevante"] == 1.9
    assert scores_by_doc["doc-menos-relevante"] == 0.4


# ---------------------------------------------------------------------------
# US-3.1: parent/child chunking -- expansión de children a su parent completo
# ---------------------------------------------------------------------------

_PARENT_DOCUMENT = {
    "id": "analysis-1--doc-1--10",
    "analysis_id": "analysis-1",
    "document_id": "doc-1",
    "page_number": 3,
    "chunk_index": 10,
    "content": "Articulo 6 completo con todos los incisos a) b) c)...",
    "chunk_type": "parent",
    "parent_chunk_id": None,
    "child_chunk_ids": ["analysis-1--doc-1--11", "analysis-1--doc-1--12"],
}


class _FakeParentChildSearchClient:
    """Simula un indice con chunks child matcheados por el retrieval, mas un
    chunk normal (sin subdividir) mezclado."""

    def __init__(self, parent_lookup: dict[str, dict] | None = None, get_document_error: bool = False) -> None:
        self.parent_lookup = parent_lookup if parent_lookup is not None else {_PARENT_DOCUMENT["id"]: _PARENT_DOCUMENT}
        # `get_document_error` se conserva como nombre por compatibilidad con
        # los tests: hoy significa "la resolución del parent falla".
        self.get_document_error = get_document_error
        self.get_document_calls: list[str] = []
        # FIX (auditoría 2026-08-13, hallazgo RET-03): los parents ya no se
        # piden con `get_document()` uno por uno, sino con UNA búsqueda por
        # lote filtrada con `search.in(id, ...)`. Se registran las llamadas
        # para poder afirmar que son pocas, no una por child.
        self.parent_lookup_calls: list[str] = []

    def search(self, **kwargs) -> Iterator[dict]:
        filter_expr = str(kwargs.get("filter") or "")
        if filter_expr.startswith("search.in(id"):
            self.parent_lookup_calls.append(filter_expr)
            if self.get_document_error:
                raise RuntimeError("simulated Azure error")
            requested = filter_expr.split("'")[1].split("|")
            return iter([self.parent_lookup[key] for key in requested if key in self.parent_lookup])

        return iter(
            [
                {
                    "@search.score": 2.0,
                    "id": "analysis-1--doc-1--11",
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 3,
                    "chunk_index": 11,
                    "content": "c) Propuesta tecnica incluyendo cronograma...",
                    "chunk_type": "child",
                    "parent_chunk_id": "analysis-1--doc-1--10",
                    "child_chunk_ids": [],
                },
                {
                    "@search.score": 1.5,
                    "id": "analysis-1--doc-1--12",
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 3,
                    "chunk_index": 12,
                    "content": "d) Declaracion de conformacion de UTE...",
                    "chunk_type": "child",
                    "parent_chunk_id": "analysis-1--doc-1--10",
                    "child_chunk_ids": [],
                },
                {
                    "@search.score": 0.8,
                    "id": "analysis-1--doc-2--0",
                    "analysis_id": "analysis-1",
                    "document_id": "doc-2",
                    "page_number": 1,
                    "chunk_index": 0,
                    "content": "Presupuesto oficial: AR$ 12.000.000",
                    "chunk_type": "normal",
                    "parent_chunk_id": None,
                    "child_chunk_ids": [],
                },
            ]
        )

    def get_document(self, key: str) -> dict:  # pragma: no cover
        raise AssertionError(
            "RET-03: la expansión children->parent ya no puede hacer una llamada por child"
        )


def test_search_expande_child_matcheado_a_su_parent_completo(monkeypatch: pytest.MonkeyPatch) -> None:
    """US-3.1: el retrieval matchea sobre el child (mas preciso), pero
    extraccion/sintesis necesitan el contexto completo del articulo -- por
    eso el resultado final tiene que traer el parent, no el fragmento."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["id", "analysis_id", "document_id", "content", "chunk_type", "parent_chunk_id", "child_chunk_ids"],
    )

    fake_client = _FakeParentChildSearchClient()
    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(query="propuesta tecnica", analysis_id="analysis-1", top_k=5)

    by_doc = {item["document_id"]: item for item in results}

    # doc-1 aparece UNA sola vez -- como el parent completo, no como los dos
    # children que matchearon (deduplicado).
    doc1_results = [item for item in results if item["document_id"] == "doc-1"]
    assert len(doc1_results) == 1
    assert doc1_results[0]["chunk_type"] == "parent"
    assert doc1_results[0]["content"] == _PARENT_DOCUMENT["content"]
    # Hereda el score del child de mayor score (2.0), no uno recalculado.
    assert doc1_results[0]["search_score"] == 2.0
    assert doc1_results[0]["matched_child_chunk_id"] == "analysis-1--doc-1--11"

    # El chunk normal (sin parent/child) pasa intacto.
    assert by_doc["doc-2"]["chunk_type"] == "normal"

    # RET-03: los parents se resuelven en UNA búsqueda por lote, no en una
    # llamada `get_document()` por child. Dos children del mismo parent ->
    # una sola llamada, con un solo id en el filtro.
    assert len(fake_client.parent_lookup_calls) == 1
    assert fake_client.parent_lookup_calls[0].count("analysis-1--doc-1--10") == 1


def test_search_conserva_child_si_falla_la_expansion_a_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el parent fue borrado o falla la red, mejor devolver el child tal
    cual (contexto parcial) que perder el resultado por completo."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(
        azure_search,
        "_search_chunk_select_fields",
        lambda: ["id", "analysis_id", "document_id", "content", "chunk_type", "parent_chunk_id", "child_chunk_ids"],
    )

    fake_client = _FakeParentChildSearchClient(get_document_error=True)
    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: fake_client)

    results = azure_search.search_hybrid(query="propuesta tecnica", analysis_id="analysis-1", top_k=5)

    doc1_results = [item for item in results if item["document_id"] == "doc-1"]
    # Sin expansion exitosa, los dos children quedan tal cual (no se dedupean
    # entre si -- son fragmentos distintos, no el mismo documento).
    assert len(doc1_results) == 2
    assert {item["chunk_type"] for item in doc1_results} == {"child"}


def test_search_sin_children_es_identico_a_antes_de_us_3_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si ningun resultado es 'child' (indice viejo, o analisis sin articulos
    subdivididos), la expansion es un no-op -- no debe llamar get_document ni
    cambiar el resultado."""
    _set_production_env(monkeypatch)
    get_settings.cache_clear()
    azure_search._azure_index_fields_cache.cache_clear()

    monkeypatch.setattr(azure_search, "_search_chunk_select_fields", lambda: ["analysis_id", "document_id", "content"])

    class _NoGetDocumentClient:
        def search(self, **kwargs) -> Iterator[dict]:
            return iter(
                [
                    {
                        "@search.score": 1.2,
                        "analysis_id": "analysis-1",
                        "document_id": "doc-1",
                        "content": "Chunk normal sin subdividir",
                    }
                ]
            )

        def get_document(self, key: str) -> dict:  # pragma: no cover
            raise AssertionError("no deberia llamarse -- no hay ningun chunk_type='child' en los resultados")

        # RET-03: sin children tampoco puede haber una búsqueda de parents.
        # `search` de arriba ignora el filtro, así que si el código intentara
        # resolver parents devolvería el chunk normal y romperia el assert final.

    import azure.search.documents as search_documents

    monkeypatch.setattr(search_documents, "SearchClient", lambda *args, **kwargs: _NoGetDocumentClient())

    results = azure_search.search_hybrid(query="cualquier cosa", analysis_id="analysis-1", top_k=5)

    assert len(results) == 1
    assert results[0]["chunk_type"] == "normal"


# ---------------------------------------------------------------------------
# REGRESIÓN RET-01 (auditoría 2026-08-13): dedupe asimétrica en la expansión
# children -> parent.
#
# `_expand_children_to_parents` deduplicaba en el orden parent->child pero no
# en child->parent: la rama de `chunk_type == "parent"` appendeaba sin
# consultar `seen_parent_ids`. Como el contenido del parent CONTIENE al del
# child, los dos matchean la misma query y el child (más corto) suele rankear
# primero por la normalización por longitud de BM25 -- así que child->parent
# es el orden esperable, no el raro.
#
# Efecto: el mismo artículo entraba dos veces al contexto del LLM, gastando dos
# slots de top_k y disparando el bonus de "dato consistente en múltiples
# fragmentos" del prompt del sistema.
# ---------------------------------------------------------------------------


class _FakeChildThenParentSearchClient:
    """El child rankea por encima de su propio parent (caso frecuente: el
    contenido del parent incluye al del child, y BM25 favorece al más corto)."""

    def __init__(self) -> None:
        self.get_document_calls: list[str] = []

    def search(self, **kwargs) -> Iterator[dict]:
        return iter(
            [
                {
                    "@search.score": 2.0,
                    "id": "analysis-1--doc-1--11",
                    "analysis_id": "analysis-1",
                    "document_id": "doc-1",
                    "page_number": 3,
                    "chunk_index": 11,
                    "content": "c) Propuesta tecnica incluyendo cronograma...",
                    "chunk_type": "child",
                    "parent_chunk_id": "analysis-1--doc-1--10",
                    "child_chunk_ids": [],
                },
                # El parent MISMO, matcheado directamente, más abajo en el ranking.
                {**_PARENT_DOCUMENT, "@search.score": 1.2},
                {
                    "@search.score": 0.8,
                    "id": "analysis-1--doc-2--0",
                    "analysis_id": "analysis-1",
                    "document_id": "doc-2",
                    "page_number": 1,
                    "chunk_index": 0,
                    "content": "Presupuesto oficial: AR$ 12.000.000",
                    "chunk_type": "normal",
                    "parent_chunk_id": None,
                    "child_chunk_ids": [],
                },
            ]
        )

    def get_document(self, key: str) -> dict:
        self.get_document_calls.append(key)
        return _PARENT_DOCUMENT


def _patch_search_client(monkeypatch: pytest.MonkeyPatch, client) -> None:
    monkeypatch.setattr(
        "shared.ports.azure_search._search_chunk_select_fields",
        lambda: ["id", "analysis_id", "document_id", "content", "chunk_type", "parent_chunk_id", "child_chunk_ids"],
    )
    monkeypatch.setattr("shared.ports.azure_search._embed_query_or_none", lambda query: None)
    monkeypatch.setattr(
        "azure.search.documents.SearchClient",
        lambda **kwargs: client,
    )


def test_parent_no_se_duplica_cuando_su_child_rankea_primero(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.ports.azure_search import search_hybrid

    client = _FakeChildThenParentSearchClient()
    _patch_search_client(monkeypatch, client)

    results = search_hybrid(query="propuesta tecnica", analysis_id="analysis-1", top_k=10)

    parent_appearances = [chunk for chunk in results if chunk["id"] == _PARENT_DOCUMENT["id"]]
    assert len(parent_appearances) == 1, (
        "el artículo entró dos veces al contexto: una expandida desde el child y "
        "otra por el match directo del parent (regresión de RET-01)"
    )

    # Y no se pierde el resto del contexto por la deduplicación.
    assert {chunk["id"] for chunk in results} == {
        _PARENT_DOCUMENT["id"],
        "analysis-1--doc-2--0",
    }


def test_parent_deduplicado_conserva_la_trazabilidad_del_child_que_matcheo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se conserva la versión expandida (la que sabe qué inciso matcheó), no
    la del match directo del parent, que no lleva esa metadata."""
    from shared.ports.azure_search import search_hybrid

    client = _FakeChildThenParentSearchClient()
    _patch_search_client(monkeypatch, client)

    results = search_hybrid(query="propuesta tecnica", analysis_id="analysis-1", top_k=10)
    parent = next(chunk for chunk in results if chunk["id"] == _PARENT_DOCUMENT["id"])

    assert parent.get("matched_child_chunk_id") == "analysis-1--doc-1--11"
    assert "Propuesta tecnica" in (parent.get("matched_child_content") or "")


def test_dos_children_del_mismo_parent_siguen_colapsando_en_uno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custodia: la dedupe que YA funcionaba (parent->child) no se rompe."""
    from shared.ports.azure_search import search_hybrid

    client = _FakeParentChildSearchClient()
    _patch_search_client(monkeypatch, client)

    results = search_hybrid(query="propuesta tecnica", analysis_id="analysis-1", top_k=10)

    parent_appearances = [chunk for chunk in results if chunk["id"] == _PARENT_DOCUMENT["id"]]
    assert len(parent_appearances) == 1
    # RET-03: una sola búsqueda por lote resuelve el parent de los dos children.
    assert len(client.parent_lookup_calls) == 1
    assert client.parent_lookup_calls[0].count("analysis-1--doc-1--10") == 1


# ---------------------------------------------------------------------------
# REGRESIÓN SYN-03 (auditoría 2026-08-13): enumeración real del índice.
#
# `_build_chunks_by_id_index` y `_build_chunks_index_from_search` usaban
# `search_hybrid(query="*", top_k=1000)` para "obtener todos los chunks". Eso
# no enumera: vectoriza el literal "*", hace kNN contra ese vector, fusiona con
# BM25 por RRF, expande children->parent (perdiendo los chunk_id de los
# children) y trunca en 1000 sin avisar. Encima se ejecutaba 8 veces por
# análisis.
# ---------------------------------------------------------------------------


class _FakeEnumerationClient:
    """Registra con qué se llamó a search() para poder afirmar que NO se usó
    búsqueda vectorial ni expansión children->parent."""

    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.search_calls: list[dict] = []
        self.get_document_calls: list[str] = []

    def search(self, **kwargs) -> Iterator[dict]:
        self.search_calls.append(kwargs)
        return iter(self.documents)

    def get_document(self, key: str) -> dict:
        self.get_document_calls.append(key)
        raise AssertionError("la enumeración no debe expandir children a parents")


def _enumeration_documents() -> list[dict]:
    return [
        {
            "id": "analysis-1--doc-1--10",
            "analysis_id": "analysis-1",
            "document_id": "doc-1",
            "page_number": 3,
            "chunk_index": 10,
            "content": "Articulo 6 completo con incisos a) b) c)",
            "chunk_type": "parent",
            "parent_chunk_id": None,
            "child_chunk_ids": ["analysis-1--doc-1--11"],
        },
        {
            "id": "analysis-1--doc-1--11",
            "analysis_id": "analysis-1",
            "document_id": "doc-1",
            "page_number": 3,
            "chunk_index": 11,
            "content": "c) Propuesta tecnica incluyendo cronograma",
            "chunk_type": "child",
            "parent_chunk_id": "analysis-1--doc-1--10",
            "child_chunk_ids": [],
        },
        {
            "id": "analysis-1--doc-2--0",
            "analysis_id": "analysis-1",
            "document_id": "doc-2",
            "page_number": 1,
            "chunk_index": 0,
            "content": "Presupuesto oficial: AR$ 12.000.000",
            "chunk_type": "normal",
            "parent_chunk_id": None,
            "child_chunk_ids": [],
        },
    ]


def _patch_enumeration(monkeypatch: pytest.MonkeyPatch, client) -> None:
    monkeypatch.setattr(
        "shared.ports.azure_search._search_chunk_select_fields",
        lambda: ["id", "analysis_id", "document_id", "page_number", "chunk_index", "content", "chunk_type", "parent_chunk_id", "child_chunk_ids"],
    )
    monkeypatch.setattr("azure.search.documents.SearchClient", lambda **kwargs: client)


def test_fetch_all_analysis_chunks_no_usa_busqueda_vectorial(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enumerar no es buscar: nada de embeddings ni de kNN."""
    from shared.ports.azure_search import fetch_all_analysis_chunks

    client = _FakeEnumerationClient(_enumeration_documents())
    _patch_enumeration(monkeypatch, client)

    def _embed_should_not_be_called(query):
        raise AssertionError(f"no se debe vectorizar nada al enumerar (recibió {query!r})")

    monkeypatch.setattr("shared.ports.azure_search._embed_query_or_none", _embed_should_not_be_called)

    chunks, truncated = fetch_all_analysis_chunks("analysis-1")

    assert not truncated
    assert len(chunks) == 3
    assert len(client.search_calls) == 1
    assert "vector_queries" not in client.search_calls[0]
    assert client.search_calls[0]["filter"] == "analysis_id eq 'analysis-1'"
    # Sin `top`: el paginador del SDK sigue los continuation tokens.
    assert "top" not in client.search_calls[0]


def test_fetch_all_analysis_chunks_conserva_children_sin_expandir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El índice debe reflejar lo que HAY, no lo que el retrieval devolvería.

    Con `search_hybrid` los children quedaban reemplazados por sus parents, así
    que sus chunk_id desaparecían del índice y las evidencias que apuntaban a
    ellos no resolvían.
    """
    from shared.ports.azure_search import fetch_all_analysis_chunks

    client = _FakeEnumerationClient(_enumeration_documents())
    _patch_enumeration(monkeypatch, client)

    chunks, _truncated = fetch_all_analysis_chunks("analysis-1")

    ids = {chunk["id"] for chunk in chunks}
    assert "analysis-1--doc-1--11" in ids, "el chunk child no puede desaparecer del índice"
    assert "analysis-1--doc-1--10" in ids
    assert client.get_document_calls == []


def test_fetch_all_analysis_chunks_escapa_comillas_en_el_filtro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.ports.azure_search import fetch_all_analysis_chunks

    client = _FakeEnumerationClient([])
    _patch_enumeration(monkeypatch, client)

    fetch_all_analysis_chunks("an'1")

    assert client.search_calls[0]["filter"] == "analysis_id eq 'an''1'"


def test_fetch_all_analysis_chunks_reporta_truncamiento(monkeypatch: pytest.MonkeyPatch) -> None:
    """El truncamiento tiene que ser visible, no silencioso."""
    import shared.ports.azure_search as azure_search_module
    from shared.ports.azure_search import fetch_all_analysis_chunks

    many = [
        {
            "id": f"analysis-1--doc-1--{i}",
            "analysis_id": "analysis-1",
            "document_id": "doc-1",
            "page_number": 1,
            "chunk_index": i,
            "content": f"chunk {i}",
            "chunk_type": "normal",
        }
        for i in range(10)
    ]
    client = _FakeEnumerationClient(many)
    _patch_enumeration(monkeypatch, client)
    monkeypatch.setattr(azure_search_module, "_MAX_ENUMERABLE_CHUNKS", 4)

    chunks, truncated = fetch_all_analysis_chunks("analysis-1")

    assert truncated is True
    assert len(chunks) == 4
