"""Tests para el retrieval híbrido RRF sobre pgvector (Historia 22.4).

Requieren Postgres local real con pgvector (Historia 22.1/22.3) -- se saltan
automáticamente si no hay conexión disponible (ver `tests/indexing/conftest.py`).
"""
from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from infra.adapters.pgvector_search import PgVectorSearchAdapter, upload_chunks
from infra.ports.pgvector_search import (
    MIN_SCORE_SMALL_ANALYSIS,
    RRF_K,
    fetch_all_analysis_chunks,
    search_hybrid,
)

# Contrato de salida esperado por `chunk_retrieval.py` (AC1) -- mismas keys
# que producía `infra/ports/azure_search.py::_document_to_chunk`.
_EXPECTED_CHUNK_KEYS = {
    "id",
    "analysis_id",
    "document_id",
    "page_number",
    "chunk_index",
    "heading_path",
    "heading_level",
    "section_path",
    "block_type",
    "table_ref",
    "blocks",
    "source",
    "primary_category",
    "secondary_categories",
    "content",
    "search_score",
    "chunk_type",
    "parent_chunk_id",
    "child_chunk_ids",
}


def _embedding(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(3072)]


def _upload(adapter, analysis_id, document_id, chunks):
    upload_chunks(chunks, analysis_id=analysis_id, correlation_id="test", adapter=adapter)


class TestSearchHybridContract:
    def test_returns_expected_keys(self, pg_session_factory, seeded_analysis):
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)
        _upload(
            adapter,
            analysis_id,
            document_id,
            [
                {
                    "document_id": document_id,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "contenido de prueba sobre plazos",
                    "embedding": _embedding(0),
                }
            ],
        )

        with patch(
            "infra.ports.pgvector_search._session_factory", return_value=pg_session_factory
        ), patch("infra.ports.pgvector_search._embed_query_or_none", return_value=_embedding(0)):
            results = search_hybrid("plazos", analysis_id, top_k=5, keyword_query="plazos")

        assert len(results) == 1
        assert set(results[0].keys()) == _EXPECTED_CHUNK_KEYS


class TestRRFFusion:
    def test_chunk_matching_both_signals_ranks_first(self, pg_session_factory, seeded_analysis):
        """AC2: score = 1/(60+rank_v) + 1/(60+rank_t); un chunk #1 en ambas
        señales gana a uno que sólo matchea una."""
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)

        target = "El plazo de presentacion de ofertas vence el 15 de marzo"
        other_text_only = "articulo generico sobre plazo administrativo sin relacion"
        other_vector_only = "contenido totalmente distinto sobre garantias bancarias"

        chunks = [
            {
                "document_id": document_id,
                "chunk_index": 0,
                "page_number": 1,
                "content": target,
                "embedding": _embedding(0),
            },
            {
                "document_id": document_id,
                "chunk_index": 1,
                "page_number": 1,
                "content": other_text_only,
                "embedding": _embedding(99),
            },
            {
                "document_id": document_id,
                "chunk_index": 2,
                "page_number": 1,
                "content": other_vector_only,
                "embedding": _embedding(1),
            },
        ]
        _upload(adapter, analysis_id, document_id, chunks)

        with patch(
            "infra.ports.pgvector_search._session_factory", return_value=pg_session_factory
        ), patch("infra.ports.pgvector_search._embed_query_or_none", return_value=_embedding(0)):
            results = search_hybrid(
                "plazo de presentacion de ofertas", analysis_id, top_k=10, keyword_query="plazo"
            )

        assert results[0]["content"] == target
        # rank 1 en vector (mismo embedding) y rank 1 en texto (mejor match léxico)
        expected_top_score = pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 1), abs=1e-9)
        assert results[0]["search_score"] == expected_top_score

    def test_min_score_small_analysis_is_documented_constant(self):
        # AC6: valor recalibrado, ver derivación en el docstring del módulo.
        assert MIN_SCORE_SMALL_ANALYSIS == 0.01


class TestParentChildExpansion:
    def test_child_expands_to_parent_with_dedup(self, pg_session_factory, seeded_analysis):
        """AC3: un child matcheado se reemplaza por su parent completo; si dos
        children del mismo parent matchean, el parent aparece una sola vez."""
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)

        # El parent NO contiene los términos de la query ni comparte su
        # embedding -- así se prueba la expansión real (el parent entra a los
        # resultados VÍA el child, no porque matchee directo él solo).
        parent_content = "Articulo 5: disposiciones administrativas generales sin relacion"
        chunks = [
            {
                "document_id": document_id,
                "chunk_index": 0,
                "page_number": 1,
                "content": parent_content,
                "embedding": _embedding(50),
                "chunk_type": "parent",
                "child_chunk_indices": [1, 2],
            },
            {
                "document_id": document_id,
                "chunk_index": 1,
                "page_number": 1,
                "content": "inciso a) garantia de mantenimiento de oferta",
                "embedding": _embedding(5),  # mismo embedding -> empata en rank vectorial
                "chunk_type": "child",
                "parent_chunk_index": 0,
            },
            {
                "document_id": document_id,
                "chunk_index": 2,
                "page_number": 1,
                "content": "inciso b) garantia de cumplimiento de contrato",
                "embedding": _embedding(5),
                "chunk_type": "child",
                "parent_chunk_index": 0,
            },
        ]
        _upload(adapter, analysis_id, document_id, chunks)

        with patch(
            "infra.ports.pgvector_search._session_factory", return_value=pg_session_factory
        ), patch("infra.ports.pgvector_search._embed_query_or_none", return_value=_embedding(5)):
            results = search_hybrid("garantia", analysis_id, top_k=10, keyword_query="garantia")

        # Los dos children matchean y ambos expanden al mismo parent -- debe
        # aparecer una sola vez (dedup).
        parent_results = [r for r in results if r["content"] == parent_content]
        assert len(parent_results) == 1
        assert "matched_child_chunk_id" in parent_results[0]


class TestFetchAllAnalysisChunks:
    def test_returns_all_chunks_without_expansion(self, pg_session_factory, seeded_analysis):
        """AC5: enumera todo, sin expandir children a parents (se quiere el
        índice tal cual está)."""
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)

        chunks = [
            {
                "document_id": document_id,
                "chunk_index": i,
                "page_number": 1,
                "content": f"contenido {i}",
                "embedding": _embedding(i),
            }
            for i in range(5)
        ]
        _upload(adapter, analysis_id, document_id, chunks)

        with patch("infra.ports.pgvector_search._session_factory", return_value=pg_session_factory):
            result_chunks, truncated = fetch_all_analysis_chunks(analysis_id)

        assert len(result_chunks) == 5
        assert truncated is False
        assert {c["content"] for c in result_chunks} == {f"contenido {i}" for i in range(5)}


class TestNoFallbackSilencioso:
    def test_embedding_failure_raises_distinct_error(self, pg_session_factory, seeded_analysis):
        """AC7: embedding fallido -> error crítico distinguible."""
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)
        _upload(
            adapter,
            analysis_id,
            document_id,
            [
                {
                    "document_id": document_id,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "algo sin relacion con la query",
                    "embedding": _embedding(0),
                }
            ],
        )

        with (
            patch("infra.ports.pgvector_search._session_factory", return_value=pg_session_factory),
            patch("infra.ports.pgvector_search._embed_query_or_none", return_value=None),
            pytest.raises(RuntimeError, match="Embedding de query falló"),
        ):
            # keyword sin match léxico alguno y sin vector -> texto vacío
            search_hybrid("xyzxyzxyz_no_deberia_matchear_nada", analysis_id, top_k=5)

    def test_analysis_without_chunks_raises_distinct_error(self, pg_session_factory, seeded_analysis):
        """AC7: análisis sin chunks indexados -> error crítico distinguible
        (embedding funcionó, pero no hay nada para ese analysis_id)."""
        analysis_id, _document_id = seeded_analysis

        with (
            patch("infra.ports.pgvector_search._session_factory", return_value=pg_session_factory),
            patch(
                "infra.ports.pgvector_search._embed_query_or_none", return_value=_embedding(0)
            ),
            pytest.raises(RuntimeError, match="no tiene chunks indexados"),
        ):
            search_hybrid("cualquier query", analysis_id, top_k=5)


class TestNoCategoryFilter:
    def test_category_param_does_not_filter_results(self, pg_session_factory, seeded_analysis):
        """AC4: `category` sólo se usa para caché de embeddings, nunca filtra
        -- un chunk de otra categoría igual puede volver."""
        analysis_id, document_id = seeded_analysis
        adapter = PgVectorSearchAdapter(session_factory=pg_session_factory)
        _upload(
            adapter,
            analysis_id,
            document_id,
            [
                {
                    "document_id": document_id,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "contenido sobre garantias bancarias",
                    "embedding": _embedding(7),
                    "primary_category": "garantias",
                }
            ],
        )

        with patch(
            "infra.ports.pgvector_search._session_factory", return_value=pg_session_factory
        ), patch("infra.ports.pgvector_search._embed_query_or_none", return_value=_embedding(7)):
            results = search_hybrid(
                "garantias bancarias",
                analysis_id,
                top_k=5,
                keyword_query="garantias",
                category="plazos_clave",  # categoría distinta a la del chunk
            )

        assert len(results) == 1
        assert results[0]["primary_category"] == "garantias"
