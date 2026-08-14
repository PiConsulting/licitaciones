"""Cobertura de `CosmosMetadataSink` (shadow-write de Cosmos en modo
dual_write/cosmos_temporal/cosmos).

FIX (auditoría 2026-08-12, flujo Cosmos): antes no existía ningún test para
este sink -- el bug de schema incompleto (faltaban analysis_name, created_at,
deleted, content_hash, file_size_bytes, sha256_hash, uploaded_at) pasó
inadvertido porque nada lo ejercitaba. Estos tests fijan el contrato completo
que `cosmos_runtime.py` espera poder leer después de un corte a cosmos_only."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from analysis.metadata_persistence import CosmosMetadataSink


class _FakeContainer:
    def __init__(self) -> None:
        self.upserted: list[dict] = []

    def upsert_item(self, item: dict) -> dict:
        self.upserted.append(item)
        return {}


def _fake_analysis(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="analysis-1",
        status="analyzed",
        current_stage="completed",
        progress_percentage=100,
        current_version_id="version-1",
        correlation_id="corr-1",
        created_by="user-1",
        extraction_metadata={"token_usage": {}},
        started_at=datetime(2026, 8, 1, tzinfo=UTC),
        timeout_at=None,
        timeout_warning_at=None,
        error_message=None,
        analysis_name="Pliego de prueba",
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        cancellation_requested=False,
        deleted_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_document(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="doc-1",
        filename="pliego.pdf",
        blob_name="analysis-1/doc-1-pliego.pdf",
        is_primary=True,
        page_count=10,
        deleted_at=None,
        file_size_bytes=123456,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by="user-1",
        uploaded_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def sink(monkeypatch: pytest.MonkeyPatch) -> tuple[CosmosMetadataSink, _FakeContainer]:
    fake_container = _FakeContainer()
    sink = CosmosMetadataSink(endpoint="https://fake", key="fake", database="db", container="container")
    monkeypatch.setattr(sink, "_get_container_client", lambda: fake_container)
    return sink, fake_container


def test_persist_analysis_incluye_todos_los_campos_que_lee_el_runtime_nativo(
    sink: tuple[CosmosMetadataSink, _FakeContainer],
) -> None:
    """`cosmos_runtime.py::list_analyses_cosmos`/`get_analysis_detail_cosmos`
    leen analysis_name, created_at y deleted directo del item -- si el shadow
    write no los escribe, un corte a cosmos_only deja esos análisis con
    nombre vacío, sin fecha para ordenar, y sin flag de borrado lógico."""
    cosmos_sink, fake_container = sink
    analysis = _fake_analysis()

    cosmos_sink.persist(analysis=analysis, documents=[], versions=[], event="analysis_completed")

    analysis_items = [item for item in fake_container.upserted if item["type"] == "analysis"]
    assert len(analysis_items) == 1
    item = analysis_items[0]

    assert item["analysis_name"] == "Pliego de prueba"
    assert item["created_at"] == "2026-07-30T00:00:00+00:00"
    assert item["cancellation_requested"] is False
    assert item["deleted"] is False


def test_persist_analysis_borrada_marca_deleted_true(
    sink: tuple[CosmosMetadataSink, _FakeContainer],
) -> None:
    cosmos_sink, fake_container = sink
    analysis = _fake_analysis(deleted_at=datetime(2026, 8, 5, tzinfo=UTC))

    cosmos_sink.persist(analysis=analysis, documents=[], versions=[], event="analysis_deleted")

    item = next(i for i in fake_container.upserted if i["type"] == "analysis")
    assert item["deleted"] is True


def test_persist_document_incluye_content_hash_para_deteccion_de_duplicados(
    sink: tuple[CosmosMetadataSink, _FakeContainer],
) -> None:
    """`find_duplicate_documents_cosmos` filtra por `c.content_hash =
    @content_hash` -- sin este campo, un documento subido en modo dual_write
    nunca se detectaría como duplicado de un archivo idéntico subido después
    en modo cosmos_only."""
    cosmos_sink, fake_container = sink
    analysis = _fake_analysis()
    document = _fake_document()

    cosmos_sink.persist(analysis=analysis, documents=[document], versions=[], event="analysis_completed")

    doc_items = [item for item in fake_container.upserted if item["type"] == "document"]
    assert len(doc_items) == 1
    item = doc_items[0]

    assert item["content_hash"] == "b" * 64
    assert item["sha256_hash"] == "a" * 64
    assert item["file_size_bytes"] == 123456
    assert item["uploaded_at"] == "2026-07-30T00:00:00+00:00"
    assert item["created_by"] == "user-1"
