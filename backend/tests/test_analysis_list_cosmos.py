from __future__ import annotations

from uuid import uuid4

from tests.conftest import FakeCosmosContainer


def _add_analysis(
    container: FakeCosmosContainer,
    *,
    user_id: str,
    status: str,
    created_at: str,
    primary_document_name: str | None = None,
    organismo: str | None = None,
) -> str:
    analysis_id = str(uuid4())
    current_version_id = None

    if primary_document_name is not None:
        doc_id = str(uuid4())
        container.add(
            {
                "id": f"document::{doc_id}",
                "type": "document",
                "partition_key": analysis_id,
                "analysis_id": analysis_id,
                "document_id": doc_id,
                "filename": primary_document_name,
                "is_primary": True,
                "uploaded_at": created_at,
                "deleted": False,
            }
        )

    if organismo is not None:
        version_id = str(uuid4())
        current_version_id = version_id
        container.add(
            {
                "id": f"version::{version_id}",
                "type": "analysis_version",
                "partition_key": analysis_id,
                "analysis_id": analysis_id,
                "version_id": version_id,
                "version_number": 1,
                "extracted_data": {"organismo": organismo},
                "conflicts": [],
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
            "current_stage": "completed",
            "progress_percentage": 100 if status == "analyzed" else 0,
            "current_version_id": current_version_id,
            "extraction_metadata": {},
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    return analysis_id


def test_list_analyses_returns_cosmos_items_instead_of_501(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    id_a = _add_analysis(
        container,
        user_id=user_id,
        status="analyzed",
        created_at="2026-01-01T00:00:00+00:00",
        primary_document_name="pliego_a.pdf",
        organismo="Ministerio A",
    )
    _add_analysis(
        container,
        user_id=user_id,
        status="draft",
        created_at="2026-02-01T00:00:00+00:00",
    )
    id_c = _add_analysis(
        container,
        user_id=user_id,
        status="analyzed",
        created_at="2026-03-01T00:00:00+00:00",
        primary_document_name="pliego_c.pdf",
    )

    response = client.get(
        "/api/v1/analyses?page=1&per_page=20&sort_by=created_at&sort_order=desc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert [item["id"] for item in payload["items"]] == [id_c, payload["items"][1]["id"], id_a]

    analyzed_a = next(item for item in payload["items"] if item["id"] == id_a)
    assert analyzed_a["primary_document_name"] == "pliego_a.pdf"
    assert analyzed_a["organismo"] == "Ministerio A"


def test_list_analyses_filters_by_status(client, cosmos_only: tuple[FakeCosmosContainer, str, str]) -> None:
    container, user_id, token = cosmos_only
    id_a = _add_analysis(container, user_id=user_id, status="analyzed", created_at="2026-01-01T00:00:00+00:00")
    _add_analysis(container, user_id=user_id, status="draft", created_at="2026-02-01T00:00:00+00:00")

    response = client.get(
        "/api/v1/analyses?status=analyzed&page=1&per_page=20",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == id_a


def test_list_analyses_search_matches_primary_document_name(
    client, cosmos_only: tuple[FakeCosmosContainer, str, str]
) -> None:
    container, user_id, token = cosmos_only
    id_a = _add_analysis(
        container,
        user_id=user_id,
        status="analyzed",
        created_at="2026-01-01T00:00:00+00:00",
        primary_document_name="pliego_licitacion_especial.pdf",
    )
    _add_analysis(
        container,
        user_id=user_id,
        status="analyzed",
        created_at="2026-02-01T00:00:00+00:00",
        primary_document_name="otro_documento.pdf",
    )

    response = client.get(
        "/api/v1/analyses?search=especial",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == id_a


def test_list_analyses_paginates(client, cosmos_only: tuple[FakeCosmosContainer, str, str]) -> None:
    container, user_id, token = cosmos_only
    for i in range(3):
        _add_analysis(
            container,
            user_id=user_id,
            status="draft",
            created_at=f"2026-0{i + 1}-01T00:00:00+00:00",
        )

    response = client.get(
        "/api/v1/analyses?page=2&per_page=1&sort_order=asc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["total_pages"] == 3
    assert len(payload["items"]) == 1
