from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from tests.conftest import FakeCosmosContainer
from users.service import get_password_hash


def _seed_analysis_with_version(
    container: FakeCosmosContainer,
    *,
    user_id: str,
    status: str = "analyzed",
) -> tuple[str, str]:
    analysis_id = str(uuid4())
    version_id = str(uuid4())

    extracted_data = {
        "requisitos_admisibilidad": [
            {
                "tipo": "constancia_fiscal",
                "valor": "Presentar constancia fiscal vigente",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 3,
                        "citation": "Se exige constancia fiscal vigente.",
                    }
                ],
            }
        ],
        "anexos_obligatorios": [
            {
                "tipo": "anexo_i",
                "valor": "Anexo I firmado",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 5,
                        "citation": "Debe incluir Anexo I firmado.",
                    }
                ],
            }
        ],
    }

    container.add(
        {
            "id": f"version::{version_id}",
            "type": "analysis_version",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "version_id": version_id,
            "version_number": 1,
            "extracted_data": extracted_data,
            "conflicts": [],
            "created_by": user_id,
            "created_at": "2026-01-01T00:00:00+00:00",
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
            "progress_percentage": 100,
            "current_version_id": version_id,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "extraction_metadata": {},
            "deleted": False,
        }
    )

    return analysis_id, version_id


def test_start_tracking_creates_overlay_and_preserves_extracted_data(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=user_id)

    before = deepcopy(container.items[f"version::{version_id}"]["extracted_data"])

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["tracking"]
    assert payload["status"] == "active"
    assert payload["analysis_id"] == analysis_id
    assert payload["summary"]["total_categories"] == 7
    assert payload["summary"]["in_review"] == 7
    assert payload["summary"]["not_reviewed"] == 0

    persisted = container.items[f"tracking::{analysis_id}::{version_id}"]
    assert persisted["type"] == "tracking"
    assert persisted["partition_key"] == analysis_id

    after = container.items[f"version::{version_id}"]["extracted_data"]
    assert after == before


def test_start_tracking_is_idempotent(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=user_id)

    response_1 = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    response_2 = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response_1.status_code == 200
    assert response_2.status_code == 200
    assert f"tracking::{analysis_id}::{version_id}" in container.items


def test_start_tracking_rejects_non_consultable_analysis(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(container, user_id=user_id, status="processing")

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TRACKING_NOT_AVAILABLE"


def test_tracking_category_transitions_and_closed_guard(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=user_id)

    start = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200

    to_closed = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "closed"},
    )
    assert to_closed.status_code == 200

    tracking = container.items[f"tracking::{analysis_id}::{version_id}"]
    item_id = tracking["categories"]["requisitos_admisibilidad"]["items"][0]["tracking_item_id"]

    blocked_item = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "compliant"},
    )
    assert blocked_item.status_code == 409
    assert blocked_item.json()["error"]["code"] == "TRACKING_CATEGORY_CLOSED"

    blocked_comment = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "checklist_item", "tracking_item_id": item_id, "content": "Comentario"},
    )
    assert blocked_comment.status_code == 409
    assert blocked_comment.json()["error"]["code"] == "TRACKING_CATEGORY_CLOSED"


def test_get_analysis_detail_includes_tracking_overlay(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(container, user_id=user_id)

    client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    detail = client.get(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["tracking"] is not None
    assert payload["tracking"]["analysis_id"] == analysis_id


def test_tracking_comments_include_author_display_name(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=user_id)

    start = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200

    created = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "category", "content": "Revisado"},
    )
    assert created.status_code == 200
    assert created.json()["created_by"] == user_id
    assert created.json()["created_by_name"] == "Cosmos User"

    legacy_id = "tracking_comment::legacy"
    container.add(
        {
            "id": legacy_id,
            "type": "tracking_comment",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "version_id": version_id,
            "category_key": "objeto_alcance",
            "scope": "category",
            "tracking_item_id": None,
            "content": "Comentario viejo",
            "created_by": user_id,
            "created_at": "2026-01-01T00:00:00+00:00",
            "deleted": False,
        }
    )

    listed = client.get(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    by_content = {item["content"]: item for item in listed.json()}
    assert by_content["Revisado"]["created_by_name"] == "Cosmos User"
    assert by_content["Comentario viejo"]["created_by_name"] == "Cosmos User"


def test_complete_tracking_success_and_audit_fields(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=user_id)

    before = deepcopy(container.items[f"version::{version_id}"]["extracted_data"])
    start = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200

    complete = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete.status_code == 200
    payload = complete.json()
    assert payload["status"] == "completed"
    assert payload["completed_by"] == user_id
    assert payload["completed_by_name"] == "Cosmos User"
    assert payload["completed_at"] is not None

    persisted = container.items[f"tracking::{analysis_id}::{version_id}"]
    assert persisted["status"] == "completed"
    assert persisted["completed_by"] == user_id
    assert any(event.get("event") == "tracking_completed" for event in persisted.get("events", []))

    after = container.items[f"version::{version_id}"]["extracted_data"]
    assert after == before


def test_completed_tracking_rejects_category_item_comment_mutations(client, cosmos_only) -> None:
    container, _user_id, token = cosmos_only
    analysis_id, version_id = _seed_analysis_with_version(container, user_id=_user_id)

    start = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200

    complete = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete.status_code == 200

    tracking = container.items[f"tracking::{analysis_id}::{version_id}"]
    item_id = tracking["categories"]["requisitos_admisibilidad"]["items"][0]["tracking_item_id"]

    blocked_category = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "closed"},
    )
    assert blocked_category.status_code == 409
    assert blocked_category.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"

    blocked_item = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "compliant"},
    )
    assert blocked_item.status_code == 409
    assert blocked_item.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"

    blocked_comment = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "checklist_item", "tracking_item_id": item_id, "content": "Comentario"},
    )
    assert blocked_comment.status_code == 409
    assert blocked_comment.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"


def test_start_tracking_returns_existing_completed_tracking(client, cosmos_only) -> None:
    _container, user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(_container, user_id=user_id)

    start = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200

    complete = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete.status_code == 200

    restart = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restart.status_code == 200
    assert restart.json()["tracking"]["status"] == "active"
    assert restart.json()["tracking"]["id"] == start.json()["tracking"]["id"]


def test_comment_edit_same_author_no_special_audit_flag(client, cosmos_only) -> None:
    _container, _user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(_container, user_id=_user_id)

    assert client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200

    created = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "category", "content": "Texto original"},
    )
    assert created.status_code == 200
    comment_id = created.json()["id"]

    edited = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "Texto editado por el mismo autor"},
    )
    assert edited.status_code == 200
    payload = edited.json()
    assert payload["created_by"] == payload["edited_by"]
    assert payload["edited_at"] is not None


def test_comment_edit_other_author_sets_audit_metadata(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(container, user_id=user_id)

    assert client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200

    created = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "category", "content": "Comentario base"},
    )
    assert created.status_code == 200
    comment_id = created.json()["id"]

    other_user_id = str(uuid4())
    container.add(
        {
            "id": f"user::{other_user_id}",
            "type": "user",
            "partition_key": f"user::{other_user_id}",
            "user_id": other_user_id,
            "email": "otro@cedia.com",
            "password_hash": get_password_hash("Test1234!"),
            "name": "Otro Usuario",
            "deleted": False,
        }
    )
    raw = container.items[comment_id]
    raw["created_by"] = other_user_id
    raw["created_by_name"] = "Otro Usuario"
    container.items[comment_id] = raw

    edited = client.patch(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "Comentario editado"},
    )
    assert edited.status_code == 200
    payload = edited.json()
    assert payload["created_by"] == other_user_id
    assert payload["edited_by"] == user_id
    assert payload["edited_by_name"] == "Cosmos User"
    assert payload["edited_at"] is not None


def test_comment_soft_delete_hides_from_list(client, cosmos_only) -> None:
    container, user_id, token = cosmos_only
    analysis_id, _version_id = _seed_analysis_with_version(container, user_id=user_id)

    assert client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/start",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200

    created = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "category", "content": "Comentario a borrar"},
    )
    assert created.status_code == 200
    comment_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204

    listed = client.get(
        f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert listed.json() == []

    persisted = container.items[comment_id]
    assert persisted["deleted"] is True
    assert persisted.get("deleted_at") is not None
    assert persisted.get("deleted_by") == user_id
