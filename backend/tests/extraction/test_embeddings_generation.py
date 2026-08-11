"""Tests para validar generación de embeddings y coherencia dimensional."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from extraction.embeddings import (
    _calculate_dynamic_batch_size,
    generate_embeddings,
    embed_query,
)


class TestDynamicBatchSize:
    """Tests para cálculo de batch size adaptativo."""

    def test_default_batch_size_for_normal_chunks(self):
        """Chunks normales (~700 tokens) usan batch size cercano al configurado."""
        chunks = [{"token_count": 700} for _ in range(100)]
        
        batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
        
        # 20000 / 700 ≈ 28, pero limitado por configured max (16)
        assert batch_size == 16  # Limitado por config

    def test_reduced_batch_size_for_large_chunks(self):
        """Chunks grandes (>1500 tokens) reducen batch size automáticamente."""
        chunks = [{"token_count": 1800} for _ in range(100)]
        
        batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
        
        # 20000 / 1800 ≈ 11
        assert batch_size == 11

    def test_minimum_batch_size_is_one(self):
        """Batch size mínimo es 1 incluso con chunks gigantes."""
        chunks = [{"token_count": 25000} for _ in range(10)]
        
        batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
        
        assert batch_size == 1

    def test_uses_sample_for_large_datasets(self):
        """Usa solo primeros 100 chunks para estimar promedio."""
        # Primeros 100: 700 tokens, resto: 2000 tokens
        chunks = [{"token_count": 700} for _ in range(100)]
        chunks.extend([{"token_count": 2000} for _ in range(400)])
        
        batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
        
        # Debe usar promedio de primeros 100 (700), no de todos
        # 20000 / 700 ≈ 28 → limitado a 16
        assert batch_size == 16

    def test_handles_missing_token_count(self):
        """Si falta token_count, usa default 700."""
        chunks = [{"content": "text"} for _ in range(50)]  # Sin token_count
        
        batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
        
        # Usa 700 como default → 20000/700 ≈ 28 → limitado a 16
        assert batch_size == 16

    def test_empty_chunks_returns_default(self):
        """Lista vacía retorna default 16."""
        chunks = []
        
        batch_size = _calculate_dynamic_batch_size(chunks)
        
        assert batch_size == 16


class TestEmbeddingGeneration:
    """Tests de integración para generate_embeddings."""

    @patch("extraction.embeddings._build_adapter")
    @patch("extraction.embeddings.get_settings")
    def test_generates_embeddings_for_all_chunks(self, mock_settings, mock_adapter):
        """Todos los chunks reciben embeddings."""
        # Setup
        mock_settings.return_value.azure_openai_retry_attempts = 3
        mock_settings.return_value.azure_openai_embeddings_batch_size = 16
        mock_settings.return_value.azure_search_embedding_dimensions = 3072
        
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.generate_embeddings.return_value = [[0.1] * 3072, [0.2] * 3072]
        
        chunks = [
            {"content": "Chunk 1", "chunk_index": 0, "token_count": 500},
            {"content": "Chunk 2", "chunk_index": 1, "token_count": 600},
        ]
        
        # Execute
        result = generate_embeddings(chunks, correlation_id="test-123")
        
        # Verify
        assert len(result) == 2
        assert "embedding" in result[0]
        assert "embedding" in result[1]
        assert len(result[0]["embedding"]) == 3072
        assert len(result[1]["embedding"]) == 3072

    @patch("extraction.embeddings._build_adapter")
    @patch("extraction.embeddings.get_settings")
    def test_validates_embedding_dimensions(self, mock_settings, mock_adapter):
        """Valida dimensiones de embeddings generados."""
        mock_settings.return_value.azure_openai_retry_attempts = 3
        mock_settings.return_value.azure_openai_embeddings_batch_size = 16
        mock_settings.return_value.azure_search_embedding_dimensions = 3072
        mock_settings.return_value.is_development = False
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        # Generar embedding con dimensiones incorrectas
        mock_adapter_instance.generate_embeddings.return_value = [[0.1] * 1536]  # Wrong dims!
        
        chunks = [{"content": "Chunk 1", "chunk_index": 0, "token_count": 500}]
        
        # Debe elevar RuntimeError por dimension mismatch
        with pytest.raises(RuntimeError, match="Embedding dimension mismatch"):
            generate_embeddings(chunks, correlation_id="test-123")

    @patch("extraction.embeddings._build_adapter")
    @patch("extraction.embeddings.get_settings")
    def test_processes_in_batches(self, mock_settings, mock_adapter):
        """Procesa chunks en batches del tamaño correcto."""
        mock_settings.return_value.azure_openai_retry_attempts = 3
        mock_settings.return_value.azure_openai_embeddings_batch_size = 2  # Batch pequeño para test
        mock_settings.return_value.azure_search_embedding_dimensions = 3072
        mock_settings.return_value.is_development = False
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        # Cada llamada genera embeddings para 2 chunks
        mock_adapter_instance.generate_embeddings.side_effect = [
            [[0.1] * 3072, [0.2] * 3072],  # Batch 1
            [[0.3] * 3072],  # Batch 2 (solo 1 chunk)
        ]
        
        chunks = [
            {"content": f"Chunk {i}", "chunk_index": i, "token_count": 500}
            for i in range(3)
        ]
        
        result = generate_embeddings(chunks, correlation_id="test-123")
        
        # Verifica que se llamó 2 veces (2 batches)
        assert mock_adapter_instance.generate_embeddings.call_count == 2
        assert len(result) == 3

    @patch("extraction.embeddings._build_adapter")
    @patch("extraction.embeddings.get_settings")
    def test_preserves_chunk_metadata(self, mock_settings, mock_adapter):
        """Preserva todos los campos del chunk original."""
        mock_settings.return_value.azure_openai_retry_attempts = 3
        mock_settings.return_value.azure_openai_embeddings_batch_size = 16
        mock_settings.return_value.azure_search_embedding_dimensions = 3072
        mock_settings.return_value.is_development = False
        
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.generate_embeddings.return_value = [[0.1] * 3072]
        
        chunks = [{
            "content": "Text",
            "chunk_index": 0,
            "document_id": "doc-123",
            "page_number": 5,
            "heading_path": ["TÍTULO"],
            "primary_category": "garantias",
            "token_count": 450,
        }]
        
        result = generate_embeddings(chunks, correlation_id="test-123")
        
        # Todos los campos originales deben estar presentes
        assert result[0]["chunk_index"] == 0
        assert result[0]["document_id"] == "doc-123"
        assert result[0]["page_number"] == 5
        assert result[0]["heading_path"] == ["TÍTULO"]
        assert result[0]["primary_category"] == "garantias"
        # Y el nuevo campo embedding
        assert "embedding" in result[0]


class TestEmbedQuery:
    """Tests para embed_query (retrieval)."""

    @patch("extraction.embeddings._build_adapter")
    def test_embeds_single_query(self, mock_adapter):
        """Vectoriza una query correctamente."""
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.generate_embeddings.return_value = [[0.5] * 3072]
        
        result = embed_query("búsqueda de garantías")
        
        # Verifica llamada con lista de 1 elemento
        mock_adapter_instance.generate_embeddings.assert_called_once_with(["búsqueda de garantías"])
        # Retorna solo el primer embedding
        assert len(result) == 3072
        assert result[0] == 0.5

    @patch("extraction.embeddings._build_adapter")
    def test_uses_same_adapter_as_chunks(self, mock_adapter):
        """Usa el mismo adapter que generate_embeddings."""
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.generate_embeddings.return_value = [[0.1] * 3072]
        
        embed_query("test")
        
        # Debe usar _build_adapter (misma fuente que chunks)
        mock_adapter.assert_called_once()


@pytest.mark.parametrize(
    "chunks_token_counts,expected_batch_size",
    [
        ([500] * 100, 16),  # Normal chunks → max batch
        ([1500] * 100, 13),  # Large chunks → reduced batch
        ([2500] * 100, 8),   # Very large chunks → smaller batch
        ([700, 1200, 500] * 33, 16),  # Mixed sizes → avg ~800 → max batch
    ],
)
def test_batch_size_parametrized(chunks_token_counts: list[int], expected_batch_size: int):
    """Tests parametrizados para diferentes distribuciones de token_count."""
    chunks = [{"token_count": count} for count in chunks_token_counts]
    
    batch_size = _calculate_dynamic_batch_size(chunks, max_tokens_per_batch=20000)
    
    assert batch_size == expected_batch_size
