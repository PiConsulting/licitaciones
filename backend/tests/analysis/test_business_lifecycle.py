from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from analysis.models import Analysis, AnalysisVersion, BusinessStatusHistory
from infra.database import SessionLocal
from users.models import User
from users.service import get_password_hash


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _test_user_id() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    user_id = user.id
    db.close()
    return user_id


def _create_analysis(
    user_id: str,
    *,
    business_status: str | None = None,
    status: str = "analyzed",
    **kwargs,
) -> str:
    db = SessionLocal()
    analysis = Analysis(
        created_by=user_id,
        status=status,
        correlation_id=str(uuid4()),
        business_status=business_status,
        **kwargs,
    )
    db.add(analysis)
    db.commit()
    analysis_id = analysis.id
    db.close()
    return analysis_id


def _presentation_payload(**overrides) -> dict:
    payload = {
        "presented_at": "2026-09-20",
        "amount": 18500000,
        "currency": "ARS",
        "channel": "compr_ar",
        "offer_number": "OF-1234",
        "notes": "Presentada en término",
    }
    payload.update(overrides)
    return payload


def _history_statuses(analysis_id: str) -> list[str]:
    db = SessionLocal()
    rows = (
        db.query(BusinessStatusHistory)
        .filter(BusinessStatusHistory.analysis_id == analysis_id)
        .order_by(BusinessStatusHistory.changed_at)
        .all()
    )
    statuses = [row.new_status for row in rows]
    db.close()
    return statuses


def test_business_state_syncs_legacy_analysis_to_pendiente_decision(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id())

    response = client.get(
        f"/api/v1/analyses/{analysis_id}/business-status", headers=_auth_headers(auth_token)
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["business_status"] == "pendiente_decision"
    assert [item["new_status"] for item in payload["history"]] == [
        "en_analisis",
        "pendiente_decision",
    ]
    assert payload["presentation"] is None
    assert payload["result"] is None


def test_business_state_keeps_en_analisis_while_phase_one_is_running(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), status="processing")

    response = client.get(
        f"/api/v1/analyses/{analysis_id}/business-status", headers=_auth_headers(auth_token)
    )

    assert response.status_code == 200
    assert response.json()["business_status"] == "en_analisis"
    assert response.json()["history"] == []


def test_business_state_sync_respects_previous_categories_decision(
    client: TestClient, auth_token: str
) -> None:
    user_id = _test_user_id()
    approved_id = _create_analysis(user_id, categories_decision="approved")
    rejected_id = _create_analysis(user_id, categories_decision="rejected")

    approved = client.get(
        f"/api/v1/analyses/{approved_id}/business-status", headers=_auth_headers(auth_token)
    )
    rejected = client.get(
        f"/api/v1/analyses/{rejected_id}/business-status", headers=_auth_headers(auth_token)
    )

    assert approved.json()["business_status"] == "en_revision"
    assert rejected.json()["business_status"] == "no_aprobada"


def test_analysis_detail_exposes_business_status(client: TestClient, auth_token: str) -> None:
    user_id = _test_user_id()
    analysis_id = _create_analysis(user_id)
    db = SessionLocal()
    version = AnalysisVersion(
        analysis_id=analysis_id,
        version_number=1,
        extracted_data={},
        conflicts=[],
        created_by=user_id,
    )
    db.add(version)
    db.commit()
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    analysis.current_version_id = version.id
    db.commit()
    db.close()

    response = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    assert response.json()["business_status"] == "pendiente_decision"


def test_note_is_stored_in_history_when_marking_no_aprobada(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="pendiente_decision")

    response = client.patch(
        f"/api/v1/analyses/{analysis_id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "no_aprobada", "note": "Fuera de alcance"},
    )
    assert response.status_code == 200

    state = client.get(
        f"/api/v1/analyses/{analysis_id}/business-status", headers=_auth_headers(auth_token)
    ).json()
    assert state["history"][-1]["new_status"] == "no_aprobada"
    assert state["history"][-1]["note"] == "Fuera de alcance"
    assert state["history"][-1]["changed_by_name"] == "Test User"


def test_presentation_moves_en_revision_to_presentada_and_stores_data(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="en_revision")

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        headers=_auth_headers(auth_token),
        json=_presentation_payload(),
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["business_status"] == "presentada"
    assert payload["presentation"]["presented_at"] == "2026-09-20"
    assert payload["presentation"]["amount"] == 18500000
    assert payload["presentation"]["channel"] == "compr_ar"
    assert payload["presentation"]["offer_number"] == "OF-1234"
    assert payload["history"][-1]["new_status"] == "presentada"
    assert payload["history"][-1]["note"] == "Presentada en término"


def test_presentation_can_be_edited_without_new_history_entry(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="en_revision")
    headers = _auth_headers(auth_token)
    client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        headers=headers,
        json=_presentation_payload(),
    )

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        headers=headers,
        json=_presentation_payload(amount=17000000, channel="bac_caba"),
    )

    assert response.status_code == 200
    assert response.json()["presentation"]["amount"] == 17000000
    assert response.json()["presentation"]["channel"] == "bac_caba"
    assert _history_statuses(analysis_id) == ["presentada"]


@pytest.mark.parametrize("current", ["pendiente_decision", "no_aprobada", "ganada", "perdida"])
def test_presentation_rejected_outside_en_revision_or_presentada(
    client: TestClient, auth_token: str, current: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status=current)

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        headers=_auth_headers(auth_token),
        json=_presentation_payload(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"


def test_presentation_rejects_invalid_channel(client: TestClient, auth_token: str) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="en_revision")

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        headers=_auth_headers(auth_token),
        json=_presentation_payload(channel="fax"),
    )

    assert response.status_code == 422


def test_result_ganada_moves_presentada_and_stores_awarded_amount(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="presentada")

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=_auth_headers(auth_token),
        json={
            "outcome": "ganada",
            "resulted_at": "2026-10-05",
            "awarded_amount": 18200000,
            "notes": "Adjudicada",
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["business_status"] == "ganada"
    assert payload["result"]["outcome"] == "ganada"
    assert payload["result"]["awarded_amount"] == 18200000
    assert payload["history"][-1]["new_status"] == "ganada"


def test_result_perdida_requires_reason_and_stores_winner(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="presentada")
    headers = _auth_headers(auth_token)

    missing_reason = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=headers,
        json={"outcome": "perdida", "resulted_at": "2026-10-05"},
    )
    assert missing_reason.status_code == 422

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=headers,
        json={
            "outcome": "perdida",
            "resulted_at": "2026-10-05",
            "loss_reason": "precio",
            "winner_name": "Constructora Sur SA",
            "winner_amount": 16900000,
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["business_status"] == "perdida"
    assert payload["result"]["loss_reason"] == "precio"
    assert payload["result"]["winner_name"] == "Constructora Sur SA"
    assert payload["result"]["winner_amount"] == 16900000


def test_result_ganada_rejects_loss_fields(client: TestClient, auth_token: str) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="presentada")

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=_auth_headers(auth_token),
        json={
            "outcome": "ganada",
            "resulted_at": "2026-10-05",
            "loss_reason": "precio",
        },
    )

    assert response.status_code == 422


def test_result_can_be_corrected_with_same_outcome_but_not_switched(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="presentada")
    headers = _auth_headers(auth_token)
    client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=headers,
        json={"outcome": "ganada", "resulted_at": "2026-10-05", "awarded_amount": 18200000},
    )

    corrected = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=headers,
        json={"outcome": "ganada", "resulted_at": "2026-10-06", "awarded_amount": 18100000},
    )
    assert corrected.status_code == 200
    assert corrected.json()["result"]["awarded_amount"] == 18100000
    assert corrected.json()["result"]["resulted_at"] == "2026-10-06"
    assert _history_statuses(analysis_id) == ["ganada"]

    switched = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=headers,
        json={"outcome": "perdida", "resulted_at": "2026-10-06", "loss_reason": "precio"},
    )
    assert switched.status_code == 400
    assert switched.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"


def test_result_rejected_before_presentation(client: TestClient, auth_token: str) -> None:
    analysis_id = _create_analysis(_test_user_id(), business_status="en_revision")

    response = client.put(
        f"/api/v1/analyses/{analysis_id}/result",
        headers=_auth_headers(auth_token),
        json={"outcome": "ganada", "resulted_at": "2026-10-05"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"


def test_categories_decision_updates_business_status(
    client: TestClient, auth_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("analysis.routes.enqueue_analysis_categories", lambda *args, **kwargs: None)
    user_id = _test_user_id()
    approved_id = _create_analysis(
        user_id, business_status="pendiente_decision", status="en_revision"
    )
    rejected_id = _create_analysis(
        user_id, business_status="pendiente_decision", status="en_revision"
    )
    headers = _auth_headers(auth_token)

    approved = client.post(
        f"/api/v1/analyses/{approved_id}/categories-decision",
        headers=headers,
        json={"decision": "approved"},
    )
    rejected = client.post(
        f"/api/v1/analyses/{rejected_id}/categories-decision",
        headers=headers,
        json={"decision": "rejected"},
    )

    assert approved.status_code == 200, approved.json()
    assert rejected.status_code == 200, rejected.json()
    assert (
        client.get(f"/api/v1/analyses/{approved_id}/business-status", headers=headers).json()[
            "business_status"
        ]
        == "en_revision"
    )
    assert (
        client.get(f"/api/v1/analyses/{rejected_id}/business-status", headers=headers).json()[
            "business_status"
        ]
        == "no_aprobada"
    )


def test_categories_decision_backfills_business_status_for_legacy_analysis(
    client: TestClient, auth_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("analysis.routes.enqueue_analysis_categories", lambda *args, **kwargs: None)
    analysis_id = _create_analysis(_test_user_id(), status="en_revision")

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/categories-decision",
        headers=_auth_headers(auth_token),
        json={"decision": "approved"},
    )

    assert response.status_code == 200, response.json()
    assert _history_statuses(analysis_id) == ["en_analisis", "pendiente_decision", "en_revision"]


def test_business_endpoints_forbidden_for_other_user(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    other = User(
        email="other-lifecycle@cedia.com",
        password_hash=get_password_hash("Test1234!"),
        name="Other User",
    )
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()
    analysis_id = _create_analysis(other_id, business_status="en_revision")
    headers = _auth_headers(auth_token)

    assert (
        client.get(f"/api/v1/analyses/{analysis_id}/business-status", headers=headers).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/v1/analyses/{analysis_id}/presentation",
            headers=headers,
            json=_presentation_payload(),
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/v1/analyses/{analysis_id}/result",
            headers=headers,
            json={"outcome": "ganada", "resulted_at": "2026-10-05"},
        ).status_code
        == 403
    )


class _FakeStorage:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def upload(self, blob_name: str, content: bytes) -> str:
        self.blobs[blob_name] = content
        return blob_name

    def delete(self, blob_name: str) -> None:
        self.blobs.pop(blob_name, None)

    def generate_download_url(self, blob_name: str) -> str:
        return f"https://storage.test/{blob_name}"


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> _FakeStorage:
    storage = _FakeStorage()
    monkeypatch.setattr("analysis.service.business_lifecycle._build_storage", lambda: storage)
    return storage


def _presented_analysis(client: TestClient, auth_token: str) -> str:
    analysis_id = _create_analysis(_test_user_id(), business_status="en_revision")
    response = client.put(
        f"/api/v1/analyses/{analysis_id}/presentation",
        json=_presentation_payload(),
        headers=_auth_headers(auth_token),
    )
    assert response.status_code == 200
    return analysis_id


def test_receipt_upload_download_and_remove(
    client: TestClient, auth_token: str, fake_storage: _FakeStorage
) -> None:
    analysis_id = _presented_analysis(client, auth_token)
    url = f"/api/v1/analyses/{analysis_id}/presentation/receipt"

    uploaded = client.post(
        url,
        files={"file": ("Constancia 1.pdf", b"%PDF-1.4 data", "application/pdf")},
        headers=_auth_headers(auth_token),
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["presentation"]["receipt_filename"] == "Constancia_1.pdf"
    assert len(fake_storage.blobs) == 1

    link = client.get(url, headers=_auth_headers(auth_token))
    assert link.status_code == 200
    assert link.json()["filename"] == "Constancia_1.pdf"
    assert link.json()["url"].startswith("https://storage.test/presentations/")

    replaced = client.post(
        url,
        files={"file": ("nueva.png", b"\x89PNG", "image/png")},
        headers=_auth_headers(auth_token),
    )
    assert replaced.json()["presentation"]["receipt_filename"] == "nueva.png"
    assert len(fake_storage.blobs) == 1

    removed = client.delete(url, headers=_auth_headers(auth_token))
    assert removed.status_code == 200
    assert removed.json()["presentation"]["receipt_filename"] is None
    assert fake_storage.blobs == {}
    assert client.get(url, headers=_auth_headers(auth_token)).status_code == 404


def test_receipt_rejects_invalid_type_and_missing_presentation(
    client: TestClient, auth_token: str, fake_storage: _FakeStorage
) -> None:
    analysis_id = _presented_analysis(client, auth_token)
    url = f"/api/v1/analyses/{analysis_id}/presentation/receipt"

    invalid = client.post(
        url,
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
        headers=_auth_headers(auth_token),
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_RECEIPT_TYPE"

    other_id = _create_analysis(_test_user_id(), business_status="en_revision")
    missing = client.post(
        f"/api/v1/analyses/{other_id}/presentation/receipt",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
        headers=_auth_headers(auth_token),
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "PRESENTATION_NOT_FOUND"
    assert fake_storage.blobs == {}
