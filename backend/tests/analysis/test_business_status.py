from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from analysis.models import Analysis, BusinessStatusHistory
from infra.business_units import BUSINESS_UNITS
from infra.database import SessionLocal
from users.models import User


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_analysis(user_id: str, *, business_status: str | None = None, **kwargs) -> Analysis:
    db = SessionLocal()
    analysis = Analysis(
        created_by=user_id,
        status="analyzed",
        correlation_id=str(uuid4()),
        business_status=business_status,
        **kwargs,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    db.close()
    return analysis


def test_update_business_status_first_transition_requires_en_analisis(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id)

    rejected = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "presentada"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"

    accepted = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "en_analisis"},
    )
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["business_status"] == "en_analisis"
    assert payload["previous_status"] is None
    assert payload["changed_by_name"] == user.name

    db = SessionLocal()
    refreshed = db.query(Analysis).filter(Analysis.id == analysis.id).first()
    assert refreshed is not None
    assert refreshed.business_status == "en_analisis"
    history = (
        db.query(BusinessStatusHistory)
        .filter(BusinessStatusHistory.analysis_id == analysis.id)
        .all()
    )
    assert len(history) == 1
    assert history[0].previous_status is None
    assert history[0].new_status == "en_analisis"
    assert history[0].changed_by == user.id
    db.close()


def test_update_business_status_happy_path_chain(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id)

    chain = [
        "en_analisis",
        "pendiente_decision",
        "en_revision",
        "presentada",
        "ganada",
    ]
    for target in chain:
        response = client.patch(
            f"/api/v1/analyses/{analysis.id}/business-status",
            headers=_auth_headers(auth_token),
            json={"business_status": target},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["business_status"] == target

    db = SessionLocal()
    history = (
        db.query(BusinessStatusHistory)
        .filter(BusinessStatusHistory.analysis_id == analysis.id)
        .order_by(BusinessStatusHistory.changed_at)
        .all()
    )
    assert len(history) == len(chain)
    assert [entry.new_status for entry in history] == chain
    db.close()


def test_update_business_status_allows_reopening_from_no_aprobada(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id, business_status="no_aprobada")

    response = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "pendiente_decision"},
    )
    assert response.status_code == 200
    assert response.json()["business_status"] == "pendiente_decision"
    assert response.json()["previous_status"] == "no_aprobada"


def test_update_business_status_rejects_terminal_state_transition(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id, business_status="ganada")

    response = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "presentada"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"

    db = SessionLocal()
    refreshed = db.query(Analysis).filter(Analysis.id == analysis.id).first()
    assert refreshed is not None
    assert refreshed.business_status == "ganada"
    history_count = (
        db.query(BusinessStatusHistory)
        .filter(BusinessStatusHistory.analysis_id == analysis.id)
        .count()
    )
    assert history_count == 0
    db.close()


def test_update_business_status_rejects_same_status_noop(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id, business_status="en_revision")

    response = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "en_revision"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BUSINESS_STATUS_TRANSITION"


def test_update_business_status_invalid_enum_value_returns_422(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    analysis = _create_analysis(user.id)

    response = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(auth_token),
        json={"business_status": "no_existe"},
    )
    assert response.status_code == 422


def test_update_business_status_hidden_for_member_of_other_unit(
    client: TestClient, auth_token: str, other_unit_member_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    db.close()
    analysis = _create_analysis(user.id, business_unit=BUSINESS_UNITS[0])

    response = client.patch(
        f"/api/v1/analyses/{analysis.id}/business-status",
        headers=_auth_headers(other_unit_member_token),
        json={"business_status": "en_analisis"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_business_status_summary_counts_by_status_and_total(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    _create_analysis(user.id, business_status="en_analisis")
    _create_analysis(user.id, business_status="en_revision")
    _create_analysis(user.id, business_status="en_revision")
    _create_analysis(user.id, business_status="ganada")
    _create_analysis(user.id, business_status=None)

    response = client.get(
        "/api/v1/analyses/business-status-summary", headers=_auth_headers(auth_token)
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert payload["by_status"]["en_analisis"] == 1
    assert payload["by_status"]["en_revision"] == 2
    assert payload["by_status"]["ganada"] == 1
    assert payload["by_status"]["presentada"] == 0
    assert payload["by_status"]["perdida"] == 0


def test_business_status_summary_filters_by_business_unit(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    _create_analysis(user.id, business_status="en_revision", business_unit="CEDI")
    _create_analysis(user.id, business_status="presentada", business_unit="PI")

    response = client.get(
        "/api/v1/analyses/business-status-summary?business_unit=CEDI",
        headers=_auth_headers(auth_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["by_status"]["en_revision"] == 1
    assert payload["by_status"]["presentada"] == 0


def test_business_status_summary_filters_by_date_range(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    older = datetime(2026, 7, 20, tzinfo=UTC)
    kept = datetime(2026, 7, 25, tzinfo=UTC)
    newer = datetime(2026, 7, 30, tzinfo=UTC)

    _create_analysis(
        user.id, business_status="en_analisis", created_at=older, updated_at=older
    )
    _create_analysis(
        user.id, business_status="en_revision", created_at=kept, updated_at=kept
    )
    _create_analysis(
        user.id, business_status="presentada", created_at=newer, updated_at=newer
    )

    response = client.get(
        "/api/v1/analyses/business-status-summary?date_from=2026-07-24&date_to=2026-07-26",
        headers=_auth_headers(auth_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["by_status"]["en_revision"] == 1
    assert payload["by_status"]["en_analisis"] == 0
    assert payload["by_status"]["presentada"] == 0


def test_business_status_summary_scoped_to_member_unit(
    client: TestClient, auth_token: str, other_unit_member_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    db.close()
    _create_analysis(user.id, business_status="ganada", business_unit=BUSINESS_UNITS[0])

    response = client.get(
        "/api/v1/analyses/business-status-summary",
        headers=_auth_headers(other_unit_member_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["by_status"]["ganada"] == 0
