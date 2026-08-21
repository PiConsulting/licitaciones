from __future__ import annotations

from uuid import uuid4

from tests.conftest import FakeCosmosContainer


def _add_analysis_with_document(
    container: FakeCosmosContainer,
    *,
    user_id: str,
    status: str,
    content_hash: str,
    filename: str = "pliego.pdf",
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> tuple[str, str]:
    analysis_id = str(uuid4())
    doc_id = str(uuid4())

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "status": status,
            "current_stage": "completed" if status == "analyzed" else "queued",
            "progress_percentage": 100 if status == "analyzed" else 0,
            "current_version_id": None,
            "cancellation_requested": False,
            "error_message": None,
            "extraction_metadata": {},
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    container.add(
        {
            "id": f"document::{doc_id}",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": doc_id,
            "filename": filename,
            "is_primary": True,
            "content_hash": content_hash,
            "created_by": user_id,
            "uploaded_at": created_at,
            "deleted": False,
        }
    )
    return analysis_id, doc_id


def test_start_analysis_flags_duplicate_of_already_analyzed_document(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    existing_id, _existing_doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="analyzed", content_hash="abc123"
    )
    new_id, new_doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="draft", content_hash="abc123", filename="pliego_nuevo.pdf"
    )

    response = client.post(
        f"/api/v1/analyses/{new_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_resolution"] is True
    assert payload["duplicates"]
    duplicate = payload["duplicates"][0]
    assert duplicate["document_id"] == new_doc_id
    assert duplicate["existing_analysis_id"] == existing_id

    # The analysis must stay in draft, not silently start processing.
    assert container.items[f"analysis::{new_id}"]["status"] == "draft"


def test_start_analysis_proceeds_when_no_duplicates(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str], monkeypatch
) -> None:
    import analysis.routes as analysis_routes

    # The real background extraction pipeline needs Document Intelligence/blob
    # config this test doesn't set up; only the queueing decision is under test.
    monkeypatch.setattr(analysis_routes, "extract_and_index_cosmos", lambda _analysis_id: None)

    container, user_id, token = cosmos_only
    analysis_id, _doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="draft", content_hash="unique-hash"
    )

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_resolution"] is False
    assert payload["status"] == "queued"
    assert container.items[f"analysis::{analysis_id}"]["status"] == "queued"


def test_start_analysis_view_existing_redirects_without_starting(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    existing_id, _ = _add_analysis_with_document(
        container, user_id=user_id, status="analyzed", content_hash="dup-hash"
    )
    new_id, new_doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="draft", content_hash="dup-hash"
    )

    response = client.post(
        f"/api/v1/analyses/{new_id}/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"decisions": [{"document_id": new_doc_id, "action": "view_existing"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["redirect_analysis_id"] == existing_id
    assert container.items[f"analysis::{new_id}"]["status"] == "draft"


def test_start_analysis_cancel_decision_soft_deletes_document(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    _existing_id, _ = _add_analysis_with_document(
        container, user_id=user_id, status="analyzed", content_hash="dup-hash-2"
    )
    new_id, new_doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="draft", content_hash="dup-hash-2"
    )

    response = client.post(
        f"/api/v1/analyses/{new_id}/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"decisions": [{"document_id": new_doc_id, "action": "cancel"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_resolution"] is False
    assert "No quedan documentos" in payload["message"]
    assert container.items[f"document::{new_doc_id}"]["deleted"] is True
    assert container.items[f"analysis::{new_id}"]["status"] == "draft"
