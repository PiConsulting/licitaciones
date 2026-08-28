"""Tests para el reranking semántico local (Historia 22.5)."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from analysis.extraction.engine.reranking import rerank_chunks


def _chunk(id_: str, content: str, **extra) -> dict:
    return {"id": id_, "content": content, "search_score": 0.5, **extra}


class TestFeatureFlag:
    def test_disabled_by_default_returns_rrf_order_truncated(self):
        chunks = [_chunk("a", "x"), _chunk("b", "y"), _chunk("c", "z")]
        with patch("analysis.extraction.engine.reranking.get_settings") as mock_settings:
            mock_settings.return_value.rag_reranking_enabled = False
            result = rerank_chunks("query", chunks, top_k=2)
        assert result == chunks[:2]

    def test_empty_chunks_returns_empty(self):
        with patch("analysis.extraction.engine.reranking.get_settings") as mock_settings:
            mock_settings.return_value.rag_reranking_enabled = True
            result = rerank_chunks("query", [], top_k=5)
        assert result == []


class TestRerankingOrdering:
    def test_reorders_by_score_and_truncates_to_top_k(self):
        chunks = [_chunk("low", "irrelevant"), _chunk("high", "relevant"), _chunk("mid", "somewhat")]

        with (
            patch("analysis.extraction.engine.reranking.get_settings") as mock_settings,
            patch(
                "analysis.extraction.engine.reranking._predict_scores",
                return_value=[0.1, 0.9, 0.5],  # scores en el mismo orden que `chunks`
            ),
        ):
            mock_settings.return_value.rag_reranking_enabled = True
            mock_settings.return_value.rag_reranking_model = "fake-model"
            mock_settings.return_value.rag_reranking_timeout_seconds = 5.0
            result = rerank_chunks("query", chunks, top_k=2)

        assert [c["id"] for c in result] == ["high", "mid"]

    def test_contract_keys_unchanged(self):
        """AC4: el reranking no agrega ni quita keys del dict de chunk."""
        chunk = _chunk("a", "text", primary_category="plazos_clave", chunk_type="normal")
        original_keys = set(chunk.keys())

        with (
            patch("analysis.extraction.engine.reranking.get_settings") as mock_settings,
            patch("analysis.extraction.engine.reranking._predict_scores", return_value=[0.7]),
        ):
            mock_settings.return_value.rag_reranking_enabled = True
            mock_settings.return_value.rag_reranking_model = "fake-model"
            mock_settings.return_value.rag_reranking_timeout_seconds = 5.0
            result = rerank_chunks("query", [chunk], top_k=1)

        assert set(result[0].keys()) == original_keys
        assert result[0] is chunk  # mismo objeto, no una copia


class TestFallbackSeguro:
    def test_model_exception_falls_back_to_rrf_order(self):
        chunks = [_chunk("a", "x"), _chunk("b", "y")]

        with (
            patch("analysis.extraction.engine.reranking.get_settings") as mock_settings,
            patch(
                "analysis.extraction.engine.reranking._predict_scores",
                side_effect=RuntimeError("modelo no disponible"),
            ),
        ):
            mock_settings.return_value.rag_reranking_enabled = True
            mock_settings.return_value.rag_reranking_model = "fake-model"
            mock_settings.return_value.rag_reranking_timeout_seconds = 5.0
            result = rerank_chunks("query", chunks, top_k=2)

        assert result == chunks[:2]

    def test_timeout_falls_back_to_rrf_order(self):
        chunks = [_chunk("a", "x"), _chunk("b", "y")]

        def _slow_predict(*_args, **_kwargs):
            time.sleep(0.3)
            return [0.9, 0.1]

        with (
            patch("analysis.extraction.engine.reranking.get_settings") as mock_settings,
            patch("analysis.extraction.engine.reranking._predict_scores", side_effect=_slow_predict),
        ):
            mock_settings.return_value.rag_reranking_enabled = True
            mock_settings.return_value.rag_reranking_model = "fake-model"
            mock_settings.return_value.rag_reranking_timeout_seconds = 0.05  # más corto que _slow_predict
            result = rerank_chunks("query", chunks, top_k=2)

        assert result == chunks[:2]


class TestRealCrossEncoderModel:
    """Smoke test con el modelo real (Historia 22.5, AC1) -- se salta si no
    hay red/el modelo no está cacheado localmente todavía."""

    def test_real_model_ranks_relevant_chunk_first(self):
        pytest.importorskip("sentence_transformers")
        model_name = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

        from analysis.extraction.engine.reranking import _load_model

        try:
            _load_model(model_name)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"modelo real no disponible en este entorno (sin red/cache): {exc}")

        chunks = [
            _chunk("noise", "La garantia de mantenimiento de oferta es del 5 por ciento"),
            _chunk("target", "El plazo de presentacion de ofertas vence el 15 de marzo"),
            _chunk("noise2", "Los pliegos de licitacion deben presentarse en formato digital"),
        ]

        with patch("analysis.extraction.engine.reranking.get_settings") as mock_settings:
            mock_settings.return_value.rag_reranking_enabled = True
            mock_settings.return_value.rag_reranking_model = model_name
            mock_settings.return_value.rag_reranking_timeout_seconds = 30.0
            result = rerank_chunks(
                "cuando vence el plazo para presentar la oferta", chunks, top_k=3
            )

        assert result[0]["id"] == "target"
