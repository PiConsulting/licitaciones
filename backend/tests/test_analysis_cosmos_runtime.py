from uuid import uuid4

from analysis import cosmos_runtime
from extraction.errors import DocumentTextExtractionError
from shared.config import get_settings


def test_extract_and_index_cosmos_uses_configured_concurrency_and_validates_prompts(
    cosmos_only,
    monkeypatch,
) -> None:
    monkeypatch.setenv("EXTRACTION_MAX_CONCURRENCY", "7")
    get_settings.cache_clear()

    container, user_id, _token = cosmos_only
    analysis_id = str(uuid4())
    correlation_id = str(uuid4())
    document_id = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "correlation_id": correlation_id,
            "status": "queued",
            "current_stage": "queued",
            "progress_percentage": 0,
            "deleted": False,
            "extraction_metadata": {},
        }
    )
    container.add(
        {
            "id": f"document::{document_id}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id,
            "blob_name": f"{analysis_id}/pliego.pdf",
            "page_count": 1,
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )

    class _FakeBlobStorage:
        def generate_download_url(self, blob_name: str) -> str:
            return f"blob://{blob_name}"

    monkeypatch.setattr(cosmos_runtime, "_build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        cosmos_runtime,
        "extract_text",
        lambda *_args, **_kwargs: [{"page_number": 1, "content": "contenido pagina"}],
    )
    monkeypatch.setattr(
        cosmos_runtime,
        "create_chunks",
        lambda *_args, **_kwargs: [
            {
                "document_id": document_id,
                "page_number": 1,
                "chunk_index": 0,
                "heading_path": [],
                "heading_level": 0,
                "section_path": "general",
                "block_type": "paragraph",
                "content": "contenido pagina",
                "token_count": 2,
            }
        ],
    )
    monkeypatch.setattr(
        cosmos_runtime,
        "generate_embeddings",
        lambda chunks, *_args, **_kwargs: [dict(chunk, embedding=[0.1, 0.2]) for chunk in chunks],
    )
    monkeypatch.setattr(cosmos_runtime, "upload_chunks", lambda *_args, **_kwargs: None)

    captured: dict = {"validated": False}

    def _validate_prompt_inventory() -> None:
        captured["validated"] = True

    def _graph_invoke(initial_state: dict, config: dict) -> dict:
        captured["state"] = initial_state
        captured["config"] = config
        return {
            "extracted_data": {"plazos": [], "plazos_extraction_status": "not_found"},
            "conflicts": [],
            "extraction_metadata": {"token_usage": {}},
        }

    monkeypatch.setattr(cosmos_runtime, "validate_prompt_inventory", _validate_prompt_inventory)
    monkeypatch.setattr(cosmos_runtime.graph, "invoke", _graph_invoke)

    cosmos_runtime.extract_and_index_cosmos(analysis_id)

    assert captured["validated"] is True
    assert captured["state"]["max_concurrency"] == 7
    assert captured["config"]["max_concurrency"] == 7

    analysis = container.items[f"analysis::{analysis_id}"]
    assert analysis["status"] == "analyzed"
    assert analysis["current_stage"] == "completed"


def test_extract_and_index_cosmos_continues_when_one_document_fails(
    cosmos_only,
    monkeypatch,
) -> None:
    container, user_id, _token = cosmos_only
    analysis_id = str(uuid4())
    correlation_id = str(uuid4())
    document_id_fail = str(uuid4())
    document_id_ok = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "correlation_id": correlation_id,
            "status": "queued",
            "current_stage": "queued",
            "progress_percentage": 0,
            "deleted": False,
            "extraction_metadata": {},
        }
    )
    container.add(
        {
            "id": f"document::{document_id_fail}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id_fail,
            "filename": "pliego-rosario.pdf",
            "blob_name": f"{analysis_id}/pliego-rosario.pdf",
            "page_count": 10,
            "is_primary": True,
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )
    container.add(
        {
            "id": f"document::{document_id_ok}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id_ok,
            "filename": "anexo-i.pdf",
            "blob_name": f"{analysis_id}/anexo-i.pdf",
            "page_count": 5,
            "is_primary": False,
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )

    class _FakeBlobStorage:
        def generate_download_url(self, blob_name: str) -> str:
            return f"blob://{blob_name}"

    monkeypatch.setattr(cosmos_runtime, "_build_blob_storage", lambda: _FakeBlobStorage())

    def _extract_text(blob_url: str, *_args, **_kwargs):
        if blob_url.endswith("pliego-rosario.pdf"):
            raise DocumentTextExtractionError("No se detectó texto útil en el documento")
        return [{"page_number": 1, "content": "contenido del anexo"}]

    monkeypatch.setattr(
        cosmos_runtime,
        "extract_text",
        _extract_text,
    )
    monkeypatch.setattr(
        cosmos_runtime,
        "create_chunks",
        lambda pages, document_id, *_args, **_kwargs: [
            {
                "document_id": document_id,
                "page_number": 1,
                "chunk_index": 0,
                "heading_path": [],
                "heading_level": 0,
                "section_path": "general",
                "block_type": "paragraph",
                "content": pages[0]["content"],
                "token_count": 3,
                "source": {"page": 1, "block_type": "paragraph", "blocks": []},
            }
        ],
    )
    monkeypatch.setattr(
        cosmos_runtime,
        "generate_embeddings",
        lambda chunks, *_args, **_kwargs: [dict(chunk, embedding=[0.1, 0.2]) for chunk in chunks],
    )
    monkeypatch.setattr(cosmos_runtime, "upload_chunks", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cosmos_runtime, "validate_prompt_inventory", lambda: None)
    monkeypatch.setattr(
        cosmos_runtime.graph,
        "invoke",
        lambda *_args, **_kwargs: {"extracted_data": {}, "conflicts": [], "extraction_metadata": {"token_usage": {}}},
    )

    cosmos_runtime.extract_and_index_cosmos(analysis_id)

    analysis = container.items[f"analysis::{analysis_id}"]
    assert analysis["status"] == "analyzed"
    assert analysis["current_stage"] == "completed"
    partial = analysis["extraction_metadata"].get("partial_extraction")
    assert partial is not None
    assert partial["failed_documents"][0]["document_id"] == document_id_fail

    failed_document = container.items[f"document::{document_id_fail}"]
    ok_document = container.items[f"document::{document_id_ok}"]
    assert failed_document["extraction_status"] == "failed"
    assert "No se detectó texto útil" in failed_document["extraction_error"]
    assert ok_document["extraction_status"] == "completed"


def test_extract_and_index_cosmos_fails_when_all_documents_fail(
    cosmos_only,
    monkeypatch,
) -> None:
    container, user_id, _token = cosmos_only
    analysis_id = str(uuid4())
    correlation_id = str(uuid4())
    document_id = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "correlation_id": correlation_id,
            "status": "queued",
            "current_stage": "queued",
            "progress_percentage": 0,
            "deleted": False,
            "extraction_metadata": {},
        }
    )
    container.add(
        {
            "id": f"document::{document_id}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id,
            "filename": "pliego.pdf",
            "blob_name": f"{analysis_id}/pliego.pdf",
            "page_count": 1,
            "is_primary": True,
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )

    class _FakeBlobStorage:
        def generate_download_url(self, blob_name: str) -> str:
            return f"blob://{blob_name}"

    monkeypatch.setattr(cosmos_runtime, "_build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        cosmos_runtime,
        "extract_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DocumentTextExtractionError("sin texto")),
    )

    cosmos_runtime.extract_and_index_cosmos(analysis_id)

    analysis = container.items[f"analysis::{analysis_id}"]
    assert analysis["status"] == "error"
    assert analysis["current_stage"] == "completed"
    assert "ningun documento" in analysis["error_message"]

    failed_document = container.items[f"document::{document_id}"]
    assert failed_document["extraction_status"] == "failed"


def test_delete_analysis_cosmos_hard_deletes_error_analysis(cosmos_only, monkeypatch) -> None:
    container, user_id, _token = cosmos_only
    analysis_id = str(uuid4())
    document_id = str(uuid4())
    version_id = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "status": "error",
            "deleted": False,
        }
    )
    container.add(
        {
            "id": f"document::{document_id}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id,
            "blob_name": f"{analysis_id}/error.pdf",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )
    container.add(
        {
            "id": f"analysis_version::{version_id}",
            "type": "analysis_version",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "version_number": 1,
        }
    )

    deleted_blobs: list[str] = []
    deleted_indexes: list[str] = []

    class _FakeBlobStorage:
        def delete(self, blob_name: str) -> None:
            deleted_blobs.append(blob_name)

    monkeypatch.setattr(cosmos_runtime, "_build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(cosmos_runtime, "delete_analysis_chunks", lambda current_id: deleted_indexes.append(current_id))

    mode = cosmos_runtime.delete_analysis_cosmos(analysis_id, user_id)

    assert mode == "hard"
    assert deleted_blobs == [f"{analysis_id}/error.pdf"]
    assert deleted_indexes == [analysis_id]
    assert f"analysis::{analysis_id}" not in container.items
    assert f"document::{document_id}" not in container.items
    assert f"analysis_version::{version_id}" not in container.items


def test_delete_analysis_cosmos_soft_deletes_completed_analysis(cosmos_only) -> None:
    container, user_id, _token = cosmos_only
    analysis_id = str(uuid4())
    document_id = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "status": "completed",
            "deleted": False,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "extraction_metadata": {},
        }
    )
    container.add(
        {
            "id": f"document::{document_id}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": document_id,
            "blob_name": f"{analysis_id}/ok.pdf",
            "uploaded_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )

    mode = cosmos_runtime.delete_analysis_cosmos(analysis_id, user_id)

    assert mode == "soft"
    assert container.items[f"analysis::{analysis_id}"]["deleted"] is True
    assert container.items[f"document::{document_id}"]["deleted"] is True

    items, total = cosmos_runtime.list_analyses_cosmos(user_id=user_id)
    assert items == []
    assert total == 0