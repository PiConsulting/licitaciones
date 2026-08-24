"""Tests para Story 12.2: BM25 como reranking opcional (no gate).

Valida que:
1. Retrieval funciona sin keyword_query (glosario vacío)
2. BM25 reranking mejora posición de chunks con keywords
3. Cálculo de BM25 local es correcto

NOTA: Estos tests NO usan el fixture de BD (evitamos conftest.py autouse).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

# Importar solo lo necesario para evitar dependencias de BD
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.ports.azure_search import _local_bm25_score


# Marcar todo el módulo para NO usar fixtures de BD
pytestmark = pytest.mark.usefixtures("_no_db_fixture")


@pytest.fixture
def _no_db_fixture():
    """Fixture vacío para prevenir autouse de setup_db."""
    pass


class TestBM25LocalScoring:
    """Tests para función _local_bm25_score."""
    
    def test_bm25_score_con_matches_completos(self):
        """BM25 debe retornar score positivo cuando todos los términos matchean."""
        chunk_text = "El oferente debe presentar garantía de mantenimiento de oferta"
        keyword_query = "garantia mantenimiento oferta"
        
        score = _local_bm25_score(chunk_text, keyword_query)
        
        assert score > 0, "BM25 score debe ser positivo cuando hay matches"
        assert score < 15, f"BM25 score debe ser razonable (< 15), got {score}"
    
    def test_bm25_score_con_matches_parciales(self):
        """BM25 debe retornar score menor cuando solo algunos términos matchean."""
        chunk_text = "El oferente debe presentar garantía de mantenimiento de oferta"
        keyword_query_completo = "garantia mantenimiento oferta"
        keyword_query_parcial = "garantia mantenimiento nomatch"
        
        score_completo = _local_bm25_score(chunk_text, keyword_query_completo)
        score_parcial = _local_bm25_score(chunk_text, keyword_query_parcial)
        
        assert score_parcial < score_completo, "Match parcial debe dar score menor que completo"
        assert score_parcial > 0, "Match parcial debe seguir dando score positivo"
    
    def test_bm25_score_sin_matches(self):
        """BM25 debe retornar 0 cuando ningún término matchea."""
        chunk_text = "El pliego establece plazos de 30 días para presentación"
        keyword_query = "garantia mantenimiento oferta"
        
        score = _local_bm25_score(chunk_text, keyword_query)
        
        assert score == 0.0, "BM25 score debe ser 0 cuando no hay términos del query"
    
    def test_bm25_score_con_query_vacio(self):
        """BM25 debe retornar 0 cuando keyword_query está vacío."""
        chunk_text = "algún contenido"
        keyword_query = ""
        
        score = _local_bm25_score(chunk_text, keyword_query)
        
        assert score == 0.0, "BM25 score debe ser 0 con query vacío"
    
    def test_bm25_score_case_insensitive(self):
        """BM25 debe ser case-insensitive."""
        chunk_text = "GARANTÍA de mantenimiento"
        keyword_query = "garantia mantenimiento"
        
        score = _local_bm25_score(chunk_text, keyword_query)
        
        assert score > 0, "BM25 debe matchear independiente de case"
    
    def test_bm25_score_con_chunk_vacio(self):
        """BM25 debe retornar 0 con chunk vacío."""
        chunk_text = ""
        keyword_query = "garantia"
        
        score = _local_bm25_score(chunk_text, keyword_query)
        
        assert score == 0.0, "BM25 debe retornar 0 con chunk vacío"


class TestSearchHybridSinGlosario:
    """Tests para validar que retrieval funciona sin keyword_query."""
    
    @patch('shared.ports.azure_search.SearchClient')
    @patch('shared.ports.azure_search._embed_query_or_none')
    def test_search_hybrid_sin_keyword_query_no_falla(self, mock_embed, mock_search_client):
        """Retrieval debe funcionar sin keyword_query (glosario vacío)."""
        # Mock embedding
        mock_embed.return_value = [0.1] * 3072  # Vector válido
        
        # Mock Azure Search results
        mock_client_instance = MagicMock()
        mock_search_client.return_value = mock_client_instance
        
        mock_results = [
            {
                "id": "chunk-1",
                "@search.score": 0.8,
                "content": "texto relevante sobre requisitos",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "primary_category": "requisitos_admisibilidad",
            },
            {
                "id": "chunk-2",
                "@search.score": 0.7,
                "content": "otro texto sobre requisitos",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 1,
                "primary_category": "requisitos_admisibilidad",
            },
        ]
        mock_client_instance.search.return_value = iter(mock_results)
        
        # Mock index fields
        with patch('shared.ports.azure_search._azure_index_fields_cache') as mock_fields:
            mock_fields.return_value = tuple([
                "id", "content", "analysis_id", "document_id", "page_number",
                "chunk_index", "primary_category", "embedding"
            ])
            
            # Ejecutar búsqueda SIN keyword_query
            chunks = search_hybrid(
                query="¿Cuáles son los requisitos?",
                analysis_id="test-analysis",
                top_k=10,
                keyword_query=None,  # Glosario vacío - clave del test
                category="requisitos_admisibilidad",
            )
        
        # Verificar que no falló y retorna chunks
        assert len(chunks) > 0, "Retrieval debe funcionar sin glosario"
        assert all(c["id"] for c in chunks), "Chunks deben tener IDs válidos"
        assert chunks[0]["id"] == "chunk-1", "Orden debe mantenerse (solo vector score)"
    
    @patch('shared.ports.azure_search.SearchClient')
    @patch('shared.ports.azure_search._embed_query_or_none')
    def test_search_hybrid_con_keyword_query_mejora_ranking(self, mock_embed, mock_search_client):
        """BM25 reranking debe mejorar posición de chunks con keywords."""
        # Mock embedding
        mock_embed.return_value = [0.1] * 3072
        
        # Mock Azure Search results
        mock_client_instance = MagicMock()
        mock_search_client.return_value = mock_client_instance
        
        # Vector search retorna chunks en orden de score vector
        # chunk-1 tiene mejor score vector PERO no tiene keywords
        # chunk-2 tiene score vector menor PERO tiene keywords del glosario
        mock_results = [
            {
                "id": "chunk-1",
                "@search.score": 0.80,
                "content": "texto genérico sin keywords específicos sobre documentación",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "primary_category": "garantias",
            },
            {
                "id": "chunk-2",
                "@search.score": 0.75,  # Score vector MENOR
                "content": "El oferente debe presentar garantía de mantenimiento de oferta mediante póliza",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 2,
                "chunk_index": 1,
                "primary_category": "garantias",
            },
            {
                "id": "chunk-3",
                "@search.score": 0.70,
                "content": "otro texto genérico",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 3,
                "chunk_index": 2,
                "primary_category": "garantias",
            },
        ]
        mock_client_instance.search.return_value = iter(mock_results)
        
        # Mock index fields
        with patch('shared.ports.azure_search._azure_index_fields_cache') as mock_fields:
            mock_fields.return_value = tuple([
                "id", "content", "analysis_id", "document_id", "page_number",
                "chunk_index", "primary_category", "embedding"
            ])
            
            # Ejecutar búsqueda CON keyword_query
            chunks = search_hybrid(
                query="¿Qué garantías debe presentar?",
                analysis_id="test-analysis",
                top_k=10,
                keyword_query="garantia mantenimiento oferta poliza",  # Keywords que matchean chunk-2
                category="garantias",
            )
        
        # chunk-2 debería rankear más alto que chunk-1 después de BM25 reranking
        chunk_ids = [c["id"] for c in chunks]
        idx_chunk1 = chunk_ids.index("chunk-1")
        idx_chunk2 = chunk_ids.index("chunk-2")
        
        assert idx_chunk2 < idx_chunk1, (
            f"BM25 debe mejorar ranking de chunk con keywords. "
            f"Orden actual: {chunk_ids}, esperado: chunk-2 antes que chunk-1"
        )


class TestBM25RerankingIntegration:
    """Tests de integración para validar pipeline completo."""
    
    @patch('shared.ports.azure_search.SearchClient')
    @patch('shared.ports.azure_search._embed_query_or_none')
    def test_pipeline_completo_con_y_sin_glosario(self, mock_embed, mock_search_client):
        """Validar que pipeline funciona correctamente con y sin glosario."""
        # Mock embedding
        mock_embed.return_value = [0.1] * 3072
        
        # Mock Azure Search
        mock_client_instance = MagicMock()
        mock_search_client.return_value = mock_client_instance
        
        mock_results = [
            {
                "id": "chunk-1",
                "@search.score": 0.8,
                "content": "organismo convocante: Ministerio de Educación",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "primary_category": "identificacion_procedimiento",
            },
            {
                "id": "chunk-2",
                "@search.score": 0.75,
                "content": "información general del procedimiento",
                "analysis_id": "test-analysis",
                "document_id": "doc-1",
                "page_number": 2,
                "chunk_index": 1,
                "primary_category": "identificacion_procedimiento",
            },
        ]
        mock_client_instance.search.return_value = iter(mock_results)
        
        # Mock index fields
        with patch('shared.ports.azure_search._azure_index_fields_cache') as mock_fields:
            mock_fields.return_value = tuple([
                "id", "content", "analysis_id", "document_id", "page_number",
                "chunk_index", "primary_category", "embedding"
            ])
            
            # Test 1: Sin glosario
            chunks_sin_glosario = search_hybrid(
                query="¿Cuál es el organismo convocante?",
                analysis_id="test-analysis",
                top_k=10,
                keyword_query=None,
                category="identificacion_procedimiento",
            )
            
            # Reset mock
            mock_client_instance.search.return_value = iter(mock_results)
            
            # Test 2: Con glosario
            chunks_con_glosario = search_hybrid(
                query="¿Cuál es el organismo convocante?",
                analysis_id="test-analysis",
                top_k=10,
                keyword_query="organismo convocante numero expediente",
                category="identificacion_procedimiento",
            )
        
        # Ambos casos deben retornar chunks
        assert len(chunks_sin_glosario) > 0, "Debe funcionar sin glosario"
        assert len(chunks_con_glosario) > 0, "Debe funcionar con glosario"
        
        # Con glosario, chunk-1 (con keywords) debe estar primero
        assert chunks_con_glosario[0]["id"] == "chunk-1", (
            "Con glosario, chunk con keywords debe rankear primero"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
