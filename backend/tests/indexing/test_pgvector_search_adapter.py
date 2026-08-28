"""Tests para PgVectorSearchAdapter (Historia 22.3).

`TestUploadChunksTransform` cubre la transformación chunk crudo -> documento
(igual lógica que `indexing/ai_search.py`, sin tocar la base) con un adapter
Mock, rápido y sin dependencias externas.

`TestPgVectorSearchAdapterRoundtrip` es el test de humo end-to-end pedido en
el AC5: requiere el Postgres local real con pgvector instalado (Historia
22.1) -- se salta automáticamente si no hay conexión disponible, para no
romper la suite en máquinas sin Postgres local corriendo. La suite global
(`tests/conftest.py`) fuerza `DATABASE_URL` a SQLite para el resto de los
tests, así que este test lee la URL real directo de `.env` en vez de usar
`get_settings()`.
"""
from __future__ import annotations

import random
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from indexing.models import Chunk
from infra.adapters.pgvector_search import PgVectorSearchAdapter, upload_chunks


class TestUploadChunksTransform:
    """Transform chunk crudo -> documento, con un adapter Mock (sin DB)."""

    def test_validates_embedding_field(self):
        chunks = [{"content": "Text", "document_id": "doc-1", "chunk_index": 0, "page_number": 1}]

        with pytest.raises(ValueError, match="missing 'embedding' field"):
            upload_chunks(chunks, analysis_id="analysis-1", correlation_id="corr-1", adapter=Mock())

    def test_builds_chunk_id_and_parent_child_ids(self):
        adapter = Mock()
        chunks = [
            {
                "document_id": "doc-1",
                "chunk_index": 5,
                "page_number": 2,
                "content": "child text",
                "embedding": [0.1] * 3072,
                "parent_chunk_index": 2,
            },
            {
                "document_id": "doc-1",
                "chunk_index": 2,
                "page_number": 2,
                "content": "parent text",
                "embedding": [0.2] * 3072,
                "child_chunk_indices": [5],
                "chunk_type": "parent",
            },
        ]

        upload_chunks(chunks, analysis_id="analysis-1", correlation_id="corr-1", adapter=adapter)

        documents = adapter.upload_chunks.call_args[0][0]
        child_doc, parent_doc = documents
        assert child_doc["id"] == "analysis-1--doc-1--5"
        assert child_doc["parent_chunk_id"] == "analysis-1--doc-1--2"
        assert parent_doc["id"] == "analysis-1--doc-1--2"
        assert parent_doc["child_chunk_ids"] == ["analysis-1--doc-1--5"]
        assert parent_doc["chunk_type"] == "parent"
        assert child_doc["chunk_type"] == "normal"  # default

    def test_deletes_stale_chunks_before_inserting(self):
        adapter = Mock()
        call_order: list[str] = []
        adapter.delete_analysis_chunks.side_effect = lambda *_: call_order.append("delete") or 0
        adapter.upload_chunks.side_effect = lambda *_: call_order.append("upload")

        chunks = [
            {
                "document_id": "doc-1",
                "chunk_index": 0,
                "page_number": 1,
                "content": "text",
                "embedding": [0.1] * 3072,
            }
        ]
        upload_chunks(chunks, analysis_id="analysis-1", correlation_id="corr-1", adapter=adapter)

        assert call_order == ["delete", "upload"]

    def test_preserves_json_fields_as_native_python(self):
        """A diferencia de ai_search.py (que hace json.dumps porque Azure Search
        espera strings), acá `table_ref`/`source` quedan como dict/list nativos
        porque las columnas destino son JSON/JSONB, no texto."""
        adapter = Mock()
        chunks = [
            {
                "document_id": "doc-1",
                "chunk_index": 0,
                "page_number": 1,
                "content": "text",
                "embedding": [0.1] * 3072,
                "table_ref": {"table_id": "t1", "row": 2},
                "source": {"page": 1, "blocks": [{"bbox": [0, 0, 1, 1]}]},
            }
        ]
        upload_chunks(chunks, analysis_id="analysis-1", correlation_id="corr-1", adapter=adapter)

        document = adapter.upload_chunks.call_args[0][0][0]
        assert document["table_ref"] == {"table_id": "t1", "row": 2}
        assert isinstance(document["source"], dict)


def _dummy_embedding() -> list[float]:
    return [random.random() for _ in range(3072)]


class TestPgVectorSearchAdapterRoundtrip:
    """AC5: test de humo end-to-end contra Postgres real."""

    def test_upload_query_and_delete_roundtrip(self, pg_session_factory, seeded_analysis):
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)
        embedding = _dummy_embedding()

        chunks = [
            {
                "document_id": document_id,
                "chunk_index": 0,
                "page_number": 1,
                "content": "Contenido de prueba del smoke test 22.3",
                "embedding": embedding,
                "title": "Título de prueba",
                "heading_path": ["Sección 1", "Subsección A"],
                "heading_level": 2,
                "section_path": "1.1",
                "block_type": "paragraph",
                "primary_category": "plazos_clave",
                "secondary_categories": ["garantias"],
                "source": {"page": 1, "block_type": "paragraph", "blocks": [{"bbox": [0, 0, 1, 1]}]},
                "chunk_type": "normal",
            }
        ]

        # AC2
        upload_chunks(chunks, analysis_id=analysis_id, correlation_id="smoke-test", adapter=adapter)

        db = pg_session_factory()
        try:
            row = db.execute(select(Chunk).where(Chunk.analysis_id == analysis_id)).scalar_one()
            assert row.id == f"{analysis_id}--{document_id}--0"
            assert row.content == "Contenido de prueba del smoke test 22.3"
            assert row.title == "Título de prueba"
            assert row.heading_path == ["Sección 1", "Subsección A"]
            assert row.heading_level == 2
            assert row.secondary_categories == ["garantias"]
            assert row.source == {
                "page": 1,
                "block_type": "paragraph",
                "blocks": [{"bbox": [0, 0, 1, 1]}],
            }
            assert row.chunk_type == "normal"
            assert len(row.embedding) == 3072
            assert row.embedding == pytest.approx(embedding, abs=1e-4)  # pgvector = float32
        finally:
            db.close()

        # AC3
        removed = adapter.delete_analysis_chunks(analysis_id)
        assert removed == 1

        db = pg_session_factory()
        try:
            remaining = (
                db.execute(select(Chunk).where(Chunk.analysis_id == analysis_id)).scalars().all()
            )
            assert remaining == []
        finally:
            db.close()

    def test_upload_replaces_previous_chunks_of_same_analysis(
        self, pg_session_factory, seeded_analysis
    ):
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)

        first_chunk = [
            {
                "document_id": document_id,
                "chunk_index": 0,
                "page_number": 1,
                "content": "version vieja",
                "embedding": _dummy_embedding(),
            }
        ]
        upload_chunks(first_chunk, analysis_id=analysis_id, correlation_id="c1", adapter=adapter)

        second_chunk = [
            {
                "document_id": document_id,
                "chunk_index": 0,
                "page_number": 1,
                "content": "version nueva",
                "embedding": _dummy_embedding(),
            }
        ]
        upload_chunks(second_chunk, analysis_id=analysis_id, correlation_id="c2", adapter=adapter)

        db = pg_session_factory()
        try:
            rows = db.execute(select(Chunk).where(Chunk.analysis_id == analysis_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].content == "version nueva"
        finally:
            db.close()
