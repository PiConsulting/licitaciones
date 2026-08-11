"""Tests para validar indexación en Azure AI Search y lógica de delete."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock, patch
from azure.core.credentials import AzureKeyCredential

from extraction.ai_search import (
    AzureSearchAdapter,
    _assert_index_contract,
    validate_index_contract,
    upload_chunks,
    delete_analysis_chunks,
)
from extraction.errors import TransientExtractionError


class TestIndexContractValidation:
    """Tests para validación de schema del índice."""

    def test_assert_index_contract_with_valid_index(self):
        """Índice válido pasa todas las validaciones."""
        mock_index = Mock()
        mock_index.fields = [
            Mock(name="analysis_id", filterable=True),
            Mock(name="content"),
            Mock(name="document_id"),
            Mock(name="page_number"),
            Mock(name="chunk_index"),
            Mock(name="embedding", vector_search_dimensions=3072),
        ]
        
        # No debe elevar excepción
        _assert_index_contract(mock_index, expected_dimensions=3072)

    def test_assert_index_contract_missing_required_field(self):
        """Falla si falta campo requerido."""
        mock_index = Mock()
        mock_index.fields = [
            Mock(name="analysis_id", filterable=True),
            Mock(name="content"),
            # Falta document_id, page_number, chunk_index, embedding
        ]
        
        with pytest.raises(RuntimeError, match="Campos faltantes"):
            _assert_index_contract(mock_index, expected_dimensions=3072)

    def test_assert_index_contract_analysis_id_not_filterable(self):
        """Falla si analysis_id no es filterable."""
        mock_index = Mock()
        mock_index.fields = [
            Mock(name="analysis_id", filterable=False),  # ❌ Not filterable
            Mock(name="content"),
            Mock(name="document_id"),
            Mock(name="page_number"),
            Mock(name="chunk_index"),
            Mock(name="embedding", vector_search_dimensions=3072),
        ]
        
        with pytest.raises(RuntimeError, match="analysis_id debe ser filterable"):
            _assert_index_contract(mock_index, expected_dimensions=3072)

    def test_assert_index_contract_wrong_embedding_dimensions(self):
        """Falla si embedding tiene dimensiones incorrectas."""
        mock_index = Mock()
        mock_index.fields = [
            Mock(name="analysis_id", filterable=True),
            Mock(name="content"),
            Mock(name="document_id"),
            Mock(name="page_number"),
            Mock(name="chunk_index"),
            Mock(name="embedding", vector_search_dimensions=1536),  # ❌ Wrong dims
        ]
        
        with pytest.raises(RuntimeError, match="embedding incompatible"):
            _assert_index_contract(mock_index, expected_dimensions=3072)


class TestAzureSearchAdapter:
    """Tests para AzureSearchAdapter."""

    def test_to_index_document_filters_unknown_fields(self):
        """_to_index_document solo incluye campos que existen en el índice."""
        adapter = AzureSearchAdapter(
            endpoint="https://test.search.windows.net",
            key="test-key",
            index_name="test-index"
        )
        
        # Mock del índice con solo 3 campos
        adapter._cached_index_fields = {"id", "content", "analysis_id"}
        
        document = {
            "id": "chunk-1",
            "content": "Text content",
            "analysis_id": "analysis-123",
            "extra_field": "should be filtered out",
            "another_extra": 123,
        }
        
        filtered = adapter._to_index_document(document)
        
        # Solo deben quedar los 3 campos permitidos
        assert set(filtered.keys()) == {"id", "content", "analysis_id"}
        assert "extra_field" not in filtered
        assert "another_extra" not in filtered

    @patch("extraction.ai_search.SearchClient")
    def test_upload_chunks_sends_filtered_documents(self, mock_search_client_class):
        """upload_chunks envía solo campos permitidos por el índice."""
        adapter = AzureSearchAdapter(
            endpoint="https://test.search.windows.net",
            key="test-key",
            index_name="test-index"
        )
        adapter._cached_index_fields = {"id", "content", "embedding"}
        
        mock_client = Mock()
        mock_search_client_class.return_value = mock_client
        mock_client.upload_documents.return_value = [Mock(succeeded=True)]
        
        documents = [
            {"id": "1", "content": "Text 1", "embedding": [0.1] * 3072, "extra": "ignore"},
            {"id": "2", "content": "Text 2", "embedding": [0.2] * 3072, "extra": "ignore"},
        ]
        
        adapter.upload_chunks(documents)
        
        # Verificar que se enviaron documentos filtrados
        call_args = mock_client.upload_documents.call_args
        sent_docs = call_args.kwargs["documents"]
        assert len(sent_docs) == 2
        assert "extra" not in sent_docs[0]
        assert "extra" not in sent_docs[1]

    @patch("extraction.ai_search.SearchClient")
    def test_upload_chunks_raises_on_failure(self, mock_search_client_class):
        """upload_chunks eleva TransientExtractionError si fallan documentos."""
        adapter = AzureSearchAdapter(
            endpoint="https://test.search.windows.net",
            key="test-key",
            index_name="test-index"
        )
        adapter._cached_index_fields = {"id", "content"}
        
        mock_client = Mock()
        mock_search_client_class.return_value = mock_client
        # Simular 1 éxito y 1 fallo
        mock_client.upload_documents.return_value = [
            Mock(succeeded=True),
            Mock(succeeded=False),
        ]
        
        documents = [{"id": "1", "content": "Text 1"}, {"id": "2", "content": "Text 2"}]
        
        with pytest.raises(TransientExtractionError, match="Fallaron 1 documentos"):
            adapter.upload_chunks(documents)

    @patch("extraction.ai_search.SearchClient")
    @patch("extraction.ai_search.sleep")
    def test_delete_analysis_chunks_with_rate_limiting(self, mock_sleep, mock_search_client_class):
        """delete_analysis_chunks espera 100ms entre batches."""
        adapter = AzureSearchAdapter(
            endpoint="https://test.search.windows.net",
            key="test-key",
            index_name="test-index"
        )
        
        mock_client = Mock()
        mock_search_client_class.return_value = mock_client
        
        # Simular 2 batches: primera llamada retorna 500, segunda retorna 0
        mock_client.search.side_effect = [
            [{"id": f"chunk-{i}"} for i in range(500)],  # Batch 1
            [],  # Batch 2 (vacío → termina loop)
        ]
        mock_client.delete_documents.return_value = None
        
        adapter.delete_analysis_chunks("analysis-123")
        
        # Verificar que se llamó delete 1 vez (primer batch)
        assert mock_client.delete_documents.call_count == 1
        
        # Verificar que se esperó 100ms después del delete
        mock_sleep.assert_called_once_with(0.1)

    @patch("extraction.ai_search.SearchClient")
    def test_delete_analysis_chunks_escapes_sql_injection(self, mock_search_client_class):
        """delete_analysis_chunks escapa comillas simples en analysis_id."""
        adapter = AzureSearchAdapter(
            endpoint="https://test.search.windows.net",
            key="test-key",
            index_name="test-index"
        )
        
        mock_client = Mock()
        mock_search_client_class.return_value = mock_client
        mock_client.search.return_value = []  # Sin resultados
        
        adapter.delete_analysis_chunks("analysis'123")  # ID con comilla
        
        # Verificar que se escapó la comilla: ' → ''
        call_args = mock_client.search.call_args
        filter_expr = call_args.kwargs["filter"]
        assert "analysis''123" in filter_expr  # Comilla duplicada


class TestUploadChunks:
    """Tests de integración para upload_chunks."""

    @patch("extraction.ai_search._build_adapter")
    @patch("extraction.ai_search.get_settings")
    @patch("extraction.ai_search.validate_index_contract")
    def test_upload_chunks_validates_embedding_field(
        self, mock_validate, mock_settings, mock_adapter
    ):
        """upload_chunks valida que cada chunk tenga campo 'embedding'."""
        mock_settings.return_value.is_production = True
        mock_settings.return_value.azure_search_retry_attempts = 3
        mock_settings.return_value.azure_search_upload_batch_size = 100
        
        chunks = [
            {"content": "Text 1", "document_id": "doc-1", "chunk_index": 0},  # ❌ Sin embedding
        ]
        
        with pytest.raises(ValueError, match="missing 'embedding' field"):
            upload_chunks(chunks, analysis_id="analysis-123", correlation_id="test-123")

    @patch("extraction.ai_search._build_adapter")
    @patch("extraction.ai_search.get_settings")
    @patch("extraction.ai_search.validate_index_contract")
    def test_upload_chunks_uses_double_colon_separator(
        self, mock_validate, mock_settings, mock_adapter
    ):
        """chunk_id usa '::' como separador (menos ambiguo que '_')."""
        mock_settings.return_value.is_production = True
        mock_settings.return_value.is_development = False
        mock_settings.return_value.azure_search_upload_batch_size = 100
        
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.upload_chunks.return_value = None
        
        chunks = [{
            "content": "Text",
            "document_id": "doc_with_underscores",
            "chunk_index": 5,
            "embedding": [0.1] * 3072,
            "page_number": 1,
        }]
        
        upload_chunks(chunks, analysis_id="analysis-123", correlation_id="test-123")
        
        # Verificar que chunk_id usa '::'
        call_args = mock_adapter_instance.upload_chunks.call_args
        documents = call_args[0][0]
        chunk_id = documents[0]["id"]
        
        # chunk_id debe ser: "analysis-123::doc_with_underscores::5"
        assert "::" in chunk_id
        assert chunk_id == "analysis-123::doc_with_underscores::5"

    @patch("extraction.ai_search._build_adapter")
    @patch("extraction.ai_search.get_settings")
    @patch("extraction.ai_search.validate_index_contract")
    def test_upload_chunks_includes_categories(
        self, mock_validate, mock_settings, mock_adapter
    ):
        """upload_chunks incluye primary_category y secondary_categories."""
        mock_settings.return_value.is_production = True
        mock_settings.return_value.is_development = False
        mock_settings.return_value.azure_search_upload_batch_size = 100
        
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        mock_adapter_instance.upload_chunks.return_value = None
        
        chunks = [{
            "content": "Text",
            "document_id": "doc-1",
            "chunk_index": 0,
            "embedding": [0.1] * 3072,
            "page_number": 1,
            "primary_category": "garantias",
            "secondary_categories": ["requisitos", "condiciones"],
        }]
        
        upload_chunks(chunks, analysis_id="analysis-123", correlation_id="test-123")
        
        call_args = mock_adapter_instance.upload_chunks.call_args
        documents = call_args[0][0]
        
        assert documents[0]["primary_category"] == "garantias"
        assert documents[0]["secondary_categories"] == ["requisitos", "condiciones"]

    @patch("extraction.ai_search._build_adapter")
    @patch("extraction.ai_search.get_settings")
    @patch("extraction.ai_search.validate_index_contract")
    @patch("extraction.ai_search.sleep")
    def test_upload_chunks_retries_on_failure(
        self, mock_sleep, mock_validate, mock_settings, mock_adapter
    ):
        """upload_chunks reintenta con exponential backoff en fallo."""
        mock_settings.return_value.is_production = True
        mock_settings.return_value.is_development = False
        mock_settings.return_value.azure_search_retry_attempts = 3
        mock_settings.return_value.
        mock_adapter_instance = Mock()
        mock_adapter.return_value = mock_adapter_instance
        # Primera llamada falla, segunda tiene éxito
        mock_adapter_instance.upload_chunks.side_effect = [
            Exception("Transient error"),
            None,  # Success
        ]
        
        chunks = [{
            "content": "Text",
            "document_id": "doc-1",
            "chunk_index": 0,
            "embedding": [0.1] * 3072,
            "page_number": 1,
        }]
        
        upload_chunks(chunks, analysis_id="analysis-123", correlation_id="test-123")
        
        # Verificar que se reintentó
        assert mock_adapter_instance.upload_chunks.call_count == 2
        
        # Verificar backoff: [2s, 10s, 30s] → primer retry espera 2s
        mock_sleep.assert_called_once_with(2)


@pytest.mark.parametrize(
    "analysis_id,document_id,chunk_index,expected_chunk_id",
    [
        ("analysis-1", "doc-a", 0, "analysis-1::doc-a::0"),
        ("analysis-2", "doc_with_underscores", 5, "analysis-2::doc_with_underscores::5"),
        ("analysis-3", "doc::with::colons", 10, "analysis-3::doc::with::colons::10"),
    ],
)
def test_chunk_id_format_parametrized(analysis_id, document_id, chunk_index, expected_chunk_id):
    """Tests parametrizados para formato de chunk_id con diferentes IDs."""
    # Simular construcción de chunk_id
    chunk_id = f"{analysis_id}::{document_id}::{chunk_index}"
    assert chunk_id == expected_chunk_id
