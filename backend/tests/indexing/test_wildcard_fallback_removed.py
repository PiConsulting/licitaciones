"""Test Story 10.3: Verificar que wildcard fallback fue eliminado."""

import pytest
from unittest.mock import patch, Mock

from infra.ports.azure_search import _search_azure


class TestWildcardFallbackRemoved:
    """Story 10.3: Wildcard fallback debe elevar RuntimeError, no degradarse."""

    @patch("infra.ports.azure_search._embed_query_or_none")
    @patch("azure.search.documents.SearchClient")
    def test_embedding_failure_raises_runtime_error(self, mock_search_client, mock_embed):
        """
        Given: _embed_query_or_none devuelve None (embedding falló)
        When: _search_azure intenta buscar
        Then: debe elevar RuntimeError con mensaje claro
        """
        # Setup: embedding falla
        mock_embed.return_value = None
        
        # Setup: Azure Search client (aunque no debería llegar a usarse)
        mock_client_instance = Mock()
        mock_search_client.return_value = mock_client_instance
        mock_client_instance.search.return_value = []  # No results
        
        # Execute & Verify
        with pytest.raises(RuntimeError) as exc_info:
            _search_azure(
                query="garantías de cumplimiento",
                analysis_id="test-123",
                top_k=10
            )
        
        # Verificar mensaje de error
        assert "Embedding de query falló" in str(exc_info.value)
        assert "retrieval no funcional" in str(exc_info.value)

    @patch("infra.ports.azure_search._embed_query_or_none")
    @patch("azure.search.documents.SearchClient")
    def test_no_chunks_indexed_raises_runtime_error(self, mock_search_client, mock_embed):
        """
        Given: embedding funciona pero búsqueda híbrida devuelve vacío
        When: _search_azure busca en un análisis sin chunks indexados
        Then: debe elevar RuntimeError indicando problema de indexación
        """
        # Setup: embedding funciona
        mock_embed.return_value = [0.1] * 3072
        
        # Setup: Azure Search devuelve 0 resultados
        mock_client_instance = Mock()
        mock_search_client.return_value = mock_client_instance
        mock_client_instance.search.return_value = []  # No chunks indexed!
        
        # Execute & Verify
        with pytest.raises(RuntimeError) as exc_info:
            _search_azure(
                query="plazos de presentación",
                analysis_id="test-456",
                top_k=10
            )
        
        # Verificar mensaje de error
        assert "no tiene chunks indexados" in str(exc_info.value)
        assert "búsqueda híbrida devolvió 0 resultados" in str(exc_info.value)

    @patch("infra.ports.azure_search._embed_query_or_none")
    @patch("azure.search.documents.SearchClient")
    def test_no_wildcard_fallback_executed(self, mock_search_client, mock_embed):
        """
        Given: embedding falla (None)
        When: _search_azure intenta buscar
        Then: NO debe ejecutar búsqueda con wildcard "*"
        """
        # Setup: embedding falla
        mock_embed.return_value = None
        
        # Setup: Azure Search client
        mock_client_instance = Mock()
        mock_search_client.return_value = mock_client_instance
        mock_client_instance.search.return_value = []
        
        # Execute (espera RuntimeError)
        try:
            _search_azure(
                query="test query",
                analysis_id="test-789",
                top_k=10
            )
        except RuntimeError:
            pass  # Esperado
        
        # Verify: NO debe haber ninguna llamada con search_text="*"
        for call in mock_client_instance.search.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get("search_text") != "*", (
                "Wildcard fallback '*' fue ejecutado — debería haber sido eliminado"
            )
