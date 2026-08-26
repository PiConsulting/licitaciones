"""Tests para módulo indexing.embeddings (Epic 11: caché LRU)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_adapter():
    """Mock de AzureEmbeddingsAdapter para evitar llamadas reales a Azure OpenAI."""
    with patch("indexing.embeddings._build_adapter") as mock_build:
        adapter = MagicMock()
        # Embedding fake de 3072 dimensiones (mismo tamaño que text-embedding-3-large)
        adapter.generate_embeddings.return_value = [[0.1] * 3072]
        mock_build.return_value = adapter
        yield adapter


def test_embed_query_cache_hit(mock_adapter):
    """Story 11.1: Verificar que cache hit NO genera llamada a Azure OpenAI.
    
    - Primera llamada: cache miss → genera HTTP request
    - Segunda llamada idéntica: cache hit → NO genera HTTP request
    
    Criterio de aceptación:
        mock_adapter.generate_embeddings llamado UNA sola vez
    """
    from indexing.embeddings import embed_query, _embed_query_cached
    
    # Limpiar cache antes del test (importante para aislamiento)
    _embed_query_cached.cache_clear()
    
    query = "¿Cuál es el plazo de presentación de ofertas?"
    analysis_id = "test-analysis-123"
    category = "plazos"
    
    # Primera llamada: cache miss
    result_1 = embed_query(query, analysis_id=analysis_id, category=category)
    assert len(result_1) == 3072
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Segunda llamada: cache hit (mismos parámetros)
    result_2 = embed_query(query, analysis_id=analysis_id, category=category)
    assert len(result_2) == 3072
    assert mock_adapter.generate_embeddings.call_count == 1  # NO aumenta
    
    # Verificar resultados idénticos (determinismo)
    assert result_1 == result_2


def test_embed_query_cache_miss_on_different_query(mock_adapter):
    """Verificar que queries distintas generan cache miss."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    analysis_id = "test-analysis-123"
    category = "plazos"
    
    # Primera query
    result_1 = embed_query("query 1", analysis_id=analysis_id, category=category)
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Query diferente: cache miss
    result_2 = embed_query("query 2", analysis_id=analysis_id, category=category)
    assert mock_adapter.generate_embeddings.call_count == 2
    
    # Resultados distintos (porque las queries son distintas)
    # (En este mock retornan lo mismo, pero en realidad serían distintos)


def test_embed_query_cache_miss_on_different_category(mock_adapter):
    """Verificar que category distinta genera cache miss (incluso con misma query)."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    query = "¿Cuál es el plazo de presentación de ofertas?"
    analysis_id = "test-analysis-123"
    
    # Misma query, category = "plazos"
    result_1 = embed_query(query, analysis_id=analysis_id, category="plazos")
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Misma query, category = "requisitos": cache miss
    result_2 = embed_query(query, analysis_id=analysis_id, category="requisitos")
    assert mock_adapter.generate_embeddings.call_count == 2


def test_embed_query_cache_miss_on_different_analysis(mock_adapter):
    """Verificar que analysis_id distinto genera cache miss."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    query = "¿Cuál es el plazo de presentación de ofertas?"
    category = "plazos"
    
    # analysis_id = "A"
    result_1 = embed_query(query, analysis_id="A", category=category)
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # analysis_id = "B": cache miss
    result_2 = embed_query(query, analysis_id="B", category=category)
    assert mock_adapter.generate_embeddings.call_count == 2


def test_embed_query_backwards_compatibility(mock_adapter):
    """Verificar retrocompatibilidad: llamar sin analysis_id/category sigue funcionando."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    query = "¿Cuál es el plazo de presentación de ofertas?"
    
    # Llamada sin parámetros opcionales (retrocompatibilidad)
    result = embed_query(query)
    assert len(result) == 3072
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Segunda llamada: cache hit (misma query, ambos None)
    result_2 = embed_query(query)
    assert mock_adapter.generate_embeddings.call_count == 1  # NO aumenta


def test_embed_query_normalized_whitespace(mock_adapter):
    """Verificar que queries con whitespace distinto comparten cache (normalización)."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    analysis_id = "test-analysis-123"
    category = "plazos"
    
    # Query con whitespace extra
    result_1 = embed_query(
        "¿Cuál  es   el plazo?",  # Dobles espacios
        analysis_id=analysis_id,
        category=category,
    )
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Query normalizada: cache hit
    result_2 = embed_query(
        "¿Cuál es el plazo?",  # Espacios normalizados
        analysis_id=analysis_id,
        category=category,
    )
    assert mock_adapter.generate_embeddings.call_count == 1  # Cache hit
    
    assert result_1 == result_2


def test_embed_query_case_insensitive(mock_adapter):
    """Verificar que queries con case distinto comparten cache (normalización lowercase)."""
    from indexing.embeddings import embed_query, _embed_query_cached
    
    _embed_query_cached.cache_clear()
    
    analysis_id = "test-analysis-123"
    category = "plazos"
    
    # Query con mayúsculas
    result_1 = embed_query(
        "¿CUÁL ES EL PLAZO?",
        analysis_id=analysis_id,
        category=category,
    )
    assert mock_adapter.generate_embeddings.call_count == 1
    
    # Query en minúsculas: cache hit
    result_2 = embed_query(
        "¿cuál es el plazo?",
        analysis_id=analysis_id,
        category=category,
    )
    assert mock_adapter.generate_embeddings.call_count == 1  # Cache hit
    
    assert result_1 == result_2
