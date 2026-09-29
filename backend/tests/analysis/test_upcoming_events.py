from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from analysis.models import Analysis
from infra.database import SessionLocal
from timeline.models_orm import EventORM
from users.models import User


def _today() -> date:
    return datetime.now().astimezone().date()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user_id() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    user_id = user.id
    db.close()
    return user_id


def _analysis(
    business_status: str | None, name: str = "Licitación", owner: str | None = None
) -> str:
    db = SessionLocal()
    analysis = Analysis(
        created_by=owner or _user_id(),
        status="analyzed",
        correlation_id=str(uuid4()),
        business_status=business_status,
        analysis_name=name,
    )
    db.add(analysis)
    db.commit()
    analysis_id = analysis.id
    db.close()
    return analysis_id


def _event(
    analysis_id: str,
    name: str,
    days_from_today: int | None,
    *,
    hidden: bool = False,
    deleted: bool = False,
) -> None:
    db = SessionLocal()
    db.add(
        EventORM(
            analysis_id=analysis_id,
            name=name,
            event_date=None
            if days_from_today is None
            else _today() + timedelta(days=days_from_today),
            date_source="detected",
            status="confirmed",
            hidden=hidden,
            deleted=deleted,
        )
    )
    db.commit()
    db.close()


def test_upcoming_events_returns_nearest_event_per_analysis(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _analysis("en_revision", "Servicio de conectividad")
    _event(analysis_id, "Presentación de ofertas", 6)
    _event(analysis_id, "Consultas", 2)
    _event(analysis_id, "Apertura de sobres", 12)

    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["analysis_id"] == analysis_id
    assert payload[0]["analysis_name"] == "Servicio de conectividad"
    assert payload[0]["event_name"] == "Consultas"
    assert payload[0]["days_until"] == 2
    assert payload[0]["additional_events"] == 2
    assert payload[0]["business_status"] == "en_revision"
    assert "business_unit" in payload[0]


def test_upcoming_events_only_for_en_revision_and_presentada(
    client: TestClient, auth_token: str
) -> None:
    for status in ("pendiente_decision", "no_aprobada", "ganada", "perdida", None):
        _event(_analysis(status), "Presentación", 3)
    revision_id = _analysis("en_revision")
    presented_id = _analysis("presentada")
    _event(revision_id, "Presentación", 3)
    _event(presented_id, "Apertura de sobres", 5)

    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(auth_token))

    assert [item["analysis_id"] for item in response.json()] == [revision_id, presented_id]


def test_upcoming_events_ignores_hidden_deleted_undated_past_and_far_events(
    client: TestClient, auth_token: str
) -> None:
    analysis_id = _analysis("en_revision")
    _event(analysis_id, "Oculto", 1, hidden=True)
    _event(analysis_id, "Borrado", 1, deleted=True)
    _event(analysis_id, "Sin fecha", None)
    _event(analysis_id, "Pasado", -1)
    _event(analysis_id, "Lejano", 16)

    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(auth_token))

    assert response.json() == []


def test_upcoming_events_window_includes_today_and_day_fifteen(
    client: TestClient, auth_token: str
) -> None:
    today_id = _analysis("en_revision", "Hoy")
    limit_id = _analysis("en_revision", "Límite")
    _event(today_id, "Cierre", 0)
    _event(limit_id, "Cierre", 15)

    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(auth_token))

    assert [(item["analysis_name"], item["days_until"]) for item in response.json()] == [
        ("Hoy", 0),
        ("Límite", 15),
    ]


def test_upcoming_events_scoped_to_current_user(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    other = User(email="otro@cedia.com", password_hash="x", name="Otro")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()
    _event(_analysis("en_revision", owner=other_id), "Presentación", 2)

    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(auth_token))

    assert response.json() == []


def test_upcoming_events_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/analyses/upcoming-events").status_code in {401, 403}
