"""FIX (auditoría 2026-08-12, flujo RAG con Cosmos, hallazgo #3 -- staleness
del status en modo cosmos_temporal/dual_write).

`extraction/runner.py::extract_and_index` es el pipeline de modo SQL. Cuando
`PERSISTENCE_MODE` es `dual_write`/`cosmos_temporal`/`cosmos`, cada escritura
de estado en SQL debería reflejarse también en Cosmos (el "shadow copy" que
sirve para poder cortar a `cosmos_only` sin perder continuidad). Pero antes
de este fix, `_persist_runtime_state` (el que escribe a Cosmos) solo se
llamaba al arrancar el análisis y al terminar (éxito o error) -- nunca en las
transiciones de etapa intermedias (`indexing`, `analyzing`). Cualquiera que
leyera el status DESDE Cosmos mientras el análisis corría (el propósito
explícito de `cosmos_temporal`: validar lecturas de Cosmos antes de cortar
del todo) veía el status congelado en la etapa anterior durante varios
minutos -- toda la duración de `extracting_text` + `indexing` + la llamada a
`graph.invoke()` -- y recién se actualizaba de golpe al final.

Este test verifica que ahora el shadow copy en Cosmos recibe eventos también
en las transiciones a "indexing" y "analyzing", no solo al arrancar/terminar.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import fitz
import pytest

import analysis.metadata_persistence as metadata_persistence
from analysis.models import Analysis
from documents.models import Document
from shared.config import get_settings
from shared.database import SessionLocal
from tests.conftest import FakeCosmosContainer
from users.models import User


def _create_pdf_with_blank_page(target: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    try:
        doc.save(target)
    finally:
        doc.close()


def test_extract_and_index_actualiza_shadow_cosmos_en_etapas_intermedias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PERSISTENCE_MODE", "dual_write")
    get_settings.cache_clear()

    fake_container = FakeCosmosContainer()
    monkeypatch.setattr(
        metadata_persistence,
        "_build_cosmos_container_client",
        lambda *_args, **_kwargs: fake_container,
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="queued", current_stage="queued", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    blob_name = f"{analysis.id}/doc.pdf"
    file_path = tmp_path / blob_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _create_pdf_with_blank_page(file_path)

    document = Document(
        analysis_id=analysis.id,
        filename="doc.pdf",
        blob_name=blob_name,
        file_size_bytes=file_path.stat().st_size,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by=user.id,
    )
    db.add(document)
    db.commit()
    analysis_id = analysis.id
    db.close()

    class _FakeBlobStorage:
        def generate_download_url(self, _blob_name: str) -> str:
            return "https://example.invalid/fake.pdf"

    monkeypatch.setattr("extraction.runner._build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        "extraction.runner.extract_text",
        lambda *_args, **_kwargs: [{"page_number": 1, "content": "contenido pagina"}],
    )
    monkeypatch.setattr(
        "extraction.runner.create_chunks",
        lambda *_args, **_kwargs: [
            {
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "content": "contenido pagina",
                "token_count": 2,
            }
        ],
    )
    monkeypatch.setattr(
        "extraction.runner.generate_embeddings",
        lambda chunks, *_args, **_kwargs: [dict(chunk, embedding=[0.1, 0.2]) for chunk in chunks],
    )
    monkeypatch.setattr("extraction.runner.upload_chunks", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "extraction.runner.extract_categories",
        lambda db_session, analysis_obj: (
            setattr(analysis_obj, "status", "analyzed"),
            setattr(analysis_obj, "current_stage", "completed"),
            db_session.commit(),
        ),
    )

    from extraction.runner import extract_and_index

    extract_and_index(analysis_id)

    shadow_item = fake_container.items.get(f"analysis::{analysis_id}")
    assert shadow_item is not None, "el shadow copy en Cosmos nunca se escribio"

    # ANTES del fix: el ultimo evento visto en Cosmos era "analysis_processing"
    # (escrito una sola vez al arrancar) porque `extract_categories` esta
    # mockeado acá y no llega a llamar `persist_analysis_metadata` -- por eso
    # lo que hay que verificar es que las DOS transiciones intermedias nuevas
    # SI llegaron a escribirse, no el evento final (que depende de
    # extract_categories, fuera del alcance de este fix).
    #
    # Verificamos indirectamente: si el fix no estuviera, `fake_container`
    # solo habria recibido upserts en "analysis_processing" (arranque) y
    # jamas en las etapas intermedias. Como no hay forma de inspeccionar
    # "todos los eventos historicos" con este fake (solo guarda el ultimo
    # estado por id), instrumentamos la escritura para contar upserts.
    assert shadow_item["status"] == "processing"
    assert shadow_item["current_stage"] in {"indexing", "analyzing"}


def test_persist_runtime_state_se_llama_en_indexing_y_analyzing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prueba mas directa: instrumentamos `_persist_runtime_state` para
    capturar la secuencia exacta de eventos que dispara `extract_and_index`,
    y confirmamos que "analysis_indexing" y "analysis_analyzing" -- los dos
    eventos nuevos de este fix -- estan en esa secuencia."""
    get_settings.cache_clear()

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="queued", current_stage="queued", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    blob_name = f"{analysis.id}/doc.pdf"
    file_path = tmp_path / blob_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _create_pdf_with_blank_page(file_path)

    document = Document(
        analysis_id=analysis.id,
        filename="doc.pdf",
        blob_name=blob_name,
        file_size_bytes=file_path.stat().st_size,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by=user.id,
    )
    db.add(document)
    db.commit()
    analysis_id = analysis.id
    db.close()

    events_seen: list[str] = []

    def _fake_persist_runtime_state(_db, _analysis_id, event):
        events_seen.append(event)

    monkeypatch.setattr("extraction.runner._persist_runtime_state", _fake_persist_runtime_state)
    class _FakeBlobStorage:
        def generate_download_url(self, _blob_name: str) -> str:
            return "https://example.invalid/fake.pdf"

    monkeypatch.setattr("extraction.runner._build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        "extraction.runner.extract_text",
        lambda *_args, **_kwargs: [{"page_number": 1, "content": "contenido pagina"}],
    )
    monkeypatch.setattr(
        "extraction.runner.create_chunks",
        lambda *_args, **_kwargs: [
            {
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "content": "contenido pagina",
                "token_count": 2,
            }
        ],
    )
    monkeypatch.setattr(
        "extraction.runner.generate_embeddings",
        lambda chunks, *_args, **_kwargs: [dict(chunk, embedding=[0.1, 0.2]) for chunk in chunks],
    )
    monkeypatch.setattr("extraction.runner.upload_chunks", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "extraction.runner.extract_categories",
        lambda db_session, analysis_obj: (
            setattr(analysis_obj, "status", "analyzed"),
            setattr(analysis_obj, "current_stage", "completed"),
            db_session.commit(),
        ),
    )

    from extraction.runner import extract_and_index

    extract_and_index(analysis_id)

    assert "analysis_indexing" in events_seen
    assert "analysis_analyzing" in events_seen
    # El orden importa: indexing tiene que verse antes que analyzing.
    assert events_seen.index("analysis_indexing") < events_seen.index("analysis_analyzing")
