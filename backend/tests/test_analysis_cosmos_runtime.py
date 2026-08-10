from uuid import uuid4

from analysis import cosmos_runtime
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