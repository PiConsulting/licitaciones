"""Limpieza de chunks previos al re-indexar un análisis.

REGRESIÓN IDX-03 (auditoría 2026-08-13).

`upload_documents` de Azure AI Search es un UPSERT, y el id de cada chunk es
`{analysis_id}--{document_id}--{chunk_index}`. Un re-análisis que produjera
MENOS chunks que el anterior pisaba los primeros y dejaba vivos los sobrantes:
el índice quedaba con dos chunkings distintos del mismo documento mezclados
bajo el mismo `analysis_id`, y el retrieval devolvía fragmentos que ya no
correspondían al texto actual.

No es hipotético: `start_analysis` permite reintentar un análisis en estado
`error`, y cualquier cambio de chunking cambia la cantidad de chunks.
"""
from __future__ import annotations

import pytest

from extraction import ai_search


class _FakeAdapter:
    def __init__(self, existing: int = 0) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []
        self._existing = existing

    def upload_chunks(self, documents: list[dict]) -> None:
        self.uploaded.extend(documents)

    def delete_analysis_chunks(self, analysis_id: str) -> int:
        self.deleted.append(analysis_id)
        return self._existing


@pytest.fixture
def adapter(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(ai_search, "_build_adapter", lambda: fake)
    monkeypatch.setattr(ai_search, "validate_index_contract", lambda: None)
    return fake


def _chunk(index: int) -> dict:
    return {
        "document_id": "doc-1",
        "page_number": 1,
        "chunk_index": index,
        "content": f"contenido {index}",
        "embedding": [0.0] * 8,
        "heading_path": [],
        "heading_level": 0,
        "section_path": "general",
        "title": None,
        "block_type": "paragraph",
    }


def test_se_borran_los_chunks_previos_antes_de_subir(adapter) -> None:
    ai_search.upload_chunks([_chunk(0), _chunk(1)], "analysis-1", "corr-1")

    assert adapter.deleted == ["analysis-1"], "no se limpió el estado previo del análisis"
    assert len(adapter.uploaded) == 2


def test_el_borrado_ocurre_antes_de_la_subida(monkeypatch) -> None:
    """El orden importa: borrar DESPUÉS eliminaría lo recién subido."""
    order: list[str] = []

    class _OrderedAdapter:
        def upload_chunks(self, documents: list[dict]) -> None:
            order.append("upload")

        def delete_analysis_chunks(self, analysis_id: str) -> int:
            order.append("delete")
            return 3

    monkeypatch.setattr(ai_search, "_build_adapter", lambda: _OrderedAdapter())
    monkeypatch.setattr(ai_search, "validate_index_contract", lambda: None)

    ai_search.upload_chunks([_chunk(0)], "analysis-1", "corr-1")

    assert order == ["delete", "upload"]


def test_un_reanalisis_con_menos_chunks_no_deja_sobrantes(monkeypatch) -> None:
    """El escenario del hallazgo: el primer run generó 5 chunks, el segundo 2."""
    index: dict[str, dict] = {}

    class _StatefulAdapter:
        def upload_chunks(self, documents: list[dict]) -> None:
            for document in documents:
                index[document["id"]] = document

        def delete_analysis_chunks(self, analysis_id: str) -> int:
            stale = [key for key in index if key.startswith(f"{analysis_id}--")]
            for key in stale:
                del index[key]
            return len(stale)

    monkeypatch.setattr(ai_search, "_build_adapter", lambda: _StatefulAdapter())
    monkeypatch.setattr(ai_search, "validate_index_contract", lambda: None)

    ai_search.upload_chunks([_chunk(i) for i in range(5)], "analysis-1", "corr-1")
    assert len(index) == 5

    # Re-análisis: el chunking cambió y ahora produce 2 chunks.
    ai_search.upload_chunks([_chunk(i) for i in range(2)], "analysis-1", "corr-1")

    assert len(index) == 2, (
        f"quedaron chunks del run anterior en el índice: {sorted(index)}"
    )


def test_un_analisis_nuevo_no_se_ve_afectado(adapter) -> None:
    """En un análisis por primera vez el borrado es una búsqueda que no
    devuelve nada: barato y sin efecto."""
    ai_search.upload_chunks([_chunk(0)], "analysis-nueva", "corr-1")

    assert adapter.deleted == ["analysis-nueva"]
    assert len(adapter.uploaded) == 1


# ---------------------------------------------------------------------------
# IDX-05: el bucle de borrado tiene que cortar
# ---------------------------------------------------------------------------


class _EventuallyConsistentClient:
    """Simula la consistencia eventual: sigue devolviendo lo ya borrado."""

    def __init__(self, doc_ids: list[str], *, forget: bool = True) -> None:
        self._doc_ids = list(doc_ids)
        self._forget = forget
        self.delete_calls = 0
        self.search_calls = 0

    def search(self, **kwargs):
        self.search_calls += 1
        return iter([{"id": doc_id} for doc_id in self._doc_ids])

    def delete_documents(self, documents):
        self.delete_calls += 1
        if self._forget:
            borrados = {d["id"] for d in documents}
            self._doc_ids = [i for i in self._doc_ids if i not in borrados]


def _adapter_with(client, monkeypatch):
    import azure.search.documents as azure_search_documents

    monkeypatch.setattr(azure_search_documents, "SearchClient", lambda **kwargs: client)
    monkeypatch.setattr(ai_search, "sleep", lambda _seconds: None)
    return ai_search.AzureSearchAdapter(endpoint="https://x", key="k", index_name="i")


def test_el_borrado_termina_aunque_el_indice_no_se_actualice(monkeypatch) -> None:
    """El bucle era `while True`: si el índice seguía devolviendo documentos ya
    borrados, giraba sin corte dentro de un request HTTP."""
    client = _EventuallyConsistentClient(["a", "b"], forget=False)
    adapter = _adapter_with(client, monkeypatch)

    removed = adapter.delete_analysis_chunks("analysis-1")

    assert removed == 2
    # Una vuelta para borrar y otra para detectar que no hay progreso.
    assert client.delete_calls == 1
    assert client.search_calls == 2


def test_el_borrado_normal_saca_todo(monkeypatch) -> None:
    client = _EventuallyConsistentClient(["a", "b", "c"])
    adapter = _adapter_with(client, monkeypatch)

    assert adapter.delete_analysis_chunks("analysis-1") == 3
    assert client._doc_ids == []


def test_el_filtro_escapa_comillas_en_el_analysis_id(monkeypatch) -> None:
    captured: dict = {}

    class _CapturingClient(_EventuallyConsistentClient):
        def search(self, **kwargs):
            captured.update(kwargs)
            return super().search(**kwargs)

    adapter = _adapter_with(_CapturingClient([]), monkeypatch)
    adapter.delete_analysis_chunks("an'1")

    assert captured["filter"] == "analysis_id eq 'an''1'"
