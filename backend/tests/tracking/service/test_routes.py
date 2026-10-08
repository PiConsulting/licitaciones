"""Tests de integración HTTP para tracking sobre PostgreSQL (Historia 22.8,
AC6: contrato de API sin cambios). Equivalente SQL de la vieja
`tests/tracking/test_tracking_cosmos.py` (Cosmos, eliminada -- ver nota de
ejecución en la historia)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.tracking.service.conftest import OTHER_USER_ID, OWNER_USER_ID
from users.service import create_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def token() -> str:
    return create_access_token(OWNER_USER_ID)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestTrackingHttpFlow:
    def test_start_get_and_complete_via_http(self, client, token, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis

        start = client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))
        assert start.status_code == 200
        payload = start.json()["tracking"]
        assert payload["status"] == "active"
        assert payload["summary"]["total_categories"] == 7
        assert payload["summary"]["in_review"] == 7

        get_resp = client.get(f"/api/v1/analyses/{analysis_id}/tracking", headers=_auth(token))
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == payload["id"]

        complete = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/complete", headers=_auth(token)
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"
        assert complete.json()["completed_by_name"] == "Tracking Owner"

    def test_analysis_detail_includes_tracking_overlay(self, client, token, analyzed_analysis):
        """`GET /analyses/{id}` en modo SQL tenía `tracking` hardcodeado a
        None (bifurcación cosmos_only incompleta) -- fix incidental de esta
        historia, ver nota de ejecución."""
        analysis_id, _version_id = analyzed_analysis
        client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))

        detail = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token))
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["tracking"] is not None
        assert payload["tracking"]["analysis_id"] == analysis_id

    def test_closed_category_blocks_item_and_comment_with_409(self, client, token, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start = client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))
        tracking = start.json()["tracking"]
        item_id = next(
            c for c in tracking["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )["items"][0]["tracking_item_id"]

        to_closed = client.patch(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/status",
            headers=_auth(token),
            json={"status": "closed"},
        )
        assert to_closed.status_code == 200

        blocked_item = client.patch(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/items/{item_id}",
            headers=_auth(token),
            json={"status": "compliant"},
        )
        assert blocked_item.status_code == 409
        assert blocked_item.json()["error"]["code"] == "TRACKING_CATEGORY_CLOSED"

        blocked_comment = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/comments",
            headers=_auth(token),
            json={"scope": "category", "content": "Comentario"},
        )
        assert blocked_comment.status_code == 409
        assert blocked_comment.json()["error"]["code"] == "TRACKING_CATEGORY_CLOSED"

    def test_completed_tracking_rejects_mutations_with_409(self, client, token, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start = client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))
        tracking = start.json()["tracking"]
        item_id = next(
            c for c in tracking["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )["items"][0]["tracking_item_id"]

        complete = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/complete", headers=_auth(token)
        )
        assert complete.status_code == 200

        blocked_category = client.patch(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/status",
            headers=_auth(token),
            json={"status": "closed"},
        )
        assert blocked_category.status_code == 409
        assert blocked_category.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"

        blocked_item = client.patch(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/items/{item_id}",
            headers=_auth(token),
            json={"status": "compliant"},
        )
        assert blocked_item.status_code == 409
        assert blocked_item.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"

        blocked_comment = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/requisitos_admisibilidad/comments",
            headers=_auth(token),
            json={"scope": "category", "content": "Comentario"},
        )
        assert blocked_comment.status_code == 409
        assert blocked_comment.json()["error"]["code"] == "TRACKING_COMPLETED_READ_ONLY"

    def test_start_after_complete_reopens_same_tracking(self, client, token, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start = client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))
        client.post(f"/api/v1/analyses/{analysis_id}/tracking/complete", headers=_auth(token))

        restart = client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))
        assert restart.status_code == 200
        assert restart.json()["tracking"]["status"] == "active"
        assert restart.json()["tracking"]["id"] == start.json()["tracking"]["id"]

    def test_comment_edit_preserves_original_author_and_sets_editor(
        self, client, token, analyzed_analysis, db_session
    ):
        """Sólo el owner del análisis puede operar sobre su tracking (mismo
        modelo de ownership de siempre) -- lo que este test verifica es que
        editar un comentario cuyo autor ORIGINAL es otro usuario (simulado
        escribiendo la fila directo, como en la versión Cosmos) preserva
        `created_by`/`created_by_name` y sólo pisa los campos `edited_*`."""
        from tracking.models import TrackingComment

        analysis_id, _version_id = analyzed_analysis
        client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))

        created = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
            headers=_auth(token),
            json={"scope": "category", "content": "Comentario base"},
        )
        assert created.status_code == 200
        comment_id = created.json()["id"]

        row = db_session.query(TrackingComment).filter(TrackingComment.id == comment_id).first()
        row.created_by = OTHER_USER_ID
        row.created_by_name = "Tracking Other"
        db_session.commit()

        edited = client.patch(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments/{comment_id}",
            headers=_auth(token),
            json={"content": "Comentario editado por el owner"},
        )
        assert edited.status_code == 200
        payload = edited.json()
        assert payload["created_by"] == OTHER_USER_ID
        assert payload["edited_by"] == OWNER_USER_ID
        assert payload["edited_by_name"] == "Tracking Owner"
        assert payload["edited_at"] is not None

    def test_comment_soft_delete_hides_from_list_http(self, client, token, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        client.post(f"/api/v1/analyses/{analysis_id}/tracking/start", headers=_auth(token))

        created = client.post(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
            headers=_auth(token),
            json={"scope": "category", "content": "Comentario a borrar"},
        )
        comment_id = created.json()["id"]

        deleted = client.delete(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments/{comment_id}",
            headers=_auth(token),
        )
        assert deleted.status_code == 204

        listed = client.get(
            f"/api/v1/analyses/{analysis_id}/tracking/categories/objeto_alcance/comments",
            headers=_auth(token),
        )
        assert listed.status_code == 200
        assert listed.json() == []
