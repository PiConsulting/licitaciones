from __future__ import annotations

from uuid import uuid4

from tests.conftest import FakeCosmosContainer


def _add_analysis_with_document(
    container: FakeCosmosContainer,
    *,
    user_id: str,
    status: str,
    with_version: bool,
    filename: str = "pliego.pdf",
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> tuple[str, str]:
    analysis_id = str(uuid4())
    doc_id = str(uuid4())
    version_id = str(uuid4()) if with_version else None

    if with_version:
        container.add(
            {
                "id": f"version::{version_id}",
                "type": "analysis_version",
                "partition_key": analysis_id,
                "analysis_id": analysis_id,
                "version_id": version_id,
                "version_number": 1,
                "extracted_data": {"objeto_alcance": {"items": []}},
                "conflicts": [],
                "created_by": user_id,
                "created_at": created_at,
            }
        )

    container.add(
        {
            "id": f"analysis::{analysis_id}",
            "type": "analysis",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "created_by": user_id,
            "status": status,
            "current_stage": "completed" if with_version else "queued",
            "progress_percentage": 100 if with_version else 0,
            "current_version_id": version_id,
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
            "page_count": 5,
            "file_size_bytes": 1024,
            "uploaded_at": created_at,
            "deleted": False,
        }
    )
    return analysis_id, doc_id


def test_get_analysis_detail_returns_documents_and_version(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    analysis_id, doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="analyzed", with_version=True, filename="pliego_final.pdf"
    )

    response = client.get(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == analysis_id
    assert payload["current_version"]["extracted_data"] == {"objeto_alcance": {"items": []}}
    assert payload["documents"] == [
        {
            "id": doc_id,
            "filename": "pliego_final.pdf",
            "page_count": 5,
            "file_size_bytes": 1024,
            "is_primary": True,
        }
    ]


def test_get_analysis_detail_404_when_no_version_yet(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    analysis_id, _doc_id = _add_analysis_with_document(
        container, user_id=user_id, status="processing", with_version=False
    )

    response = client.get(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_analysis_detail_403_for_other_users_analysis(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, _user_id, token = cosmos_only
    other_user_id = str(uuid4())
    analysis_id, _doc_id = _add_analysis_with_document(
        container, user_id=other_user_id, status="analyzed", with_version=True
    )

    response = client.get(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
