from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog
from fastapi.testclient import TestClient

from analysis.models import Analysis, CurrentStage
from analysis.progress import calculate_timeout_minutes, set_timeout_timestamps, update_stage_and_progress
from shared.database import SessionLocal
from extraction.runner import check_cancellation_requested, check_timeout_exceeded, check_timeout_warning
from users.models import User

logger = structlog.get_logger(__name__)


def test_timeout_calculation_ranges() -> None:
    assert calculate_timeout_minutes(10) == 8
    assert calculate_timeout_minutes(50) == 8
    assert calculate_timeout_minutes(75) == 12
    assert calculate_timeout_minutes(100) == 12
    assert calculate_timeout_minutes(150) == 18
    assert calculate_timeout_minutes(200) == 18
    assert calculate_timeout_minutes(250) == 25


def test_set_timeout_timestamps() -> None:
    analysis = Analysis(created_by="user-1", status="queued", correlation_id=str(uuid4()))
    now = datetime.now(UTC)

    set_timeout_timestamps(analysis, 40, now=now)

    assert analysis.started_at == now
    assert analysis.timeout_at == now + timedelta(minutes=8)
    assert analysis.timeout_warning_at == now + timedelta(minutes=6)


def test_update_stage_and_progress() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="processing", current_stage="queued", progress_percentage=0)
    db.add(analysis)
    db.commit()

    updated = update_stage_and_progress(
        db,
        analysis.id,
        stage=CurrentStage.EXTRACTING_TEXT,
        progress_increment=5,
        stage_progress="Extrayendo texto (1 de 2 documentos)",
        status="processing",
    )

    assert updated is not None
    assert updated.current_stage == "extracting_text"
    assert updated.progress_percentage >= 15
    db.close()


def test_timeout_warning_triggered() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        timeout_warning_at=datetime.now(UTC) - timedelta(seconds=5),
        timeout_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    db.add(analysis)
    db.commit()

    should_warn = check_timeout_warning(db, analysis.id, logger)

    assert should_warn is True
    db.close()


def test_timeout_exceeded_sets_error() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        timeout_at=datetime.now(UTC) - timedelta(seconds=5),
        progress_percentage=35,
    )
    db.add(analysis)
    db.commit()

    exceeded = check_timeout_exceeded(db, analysis.id, logger)

    assert exceeded is True
    db.refresh(analysis)
    assert analysis.status == "error"
    assert "supero el tiempo maximo" in (analysis.error_message or "")
    db.close()


def test_cancel_endpoint_success(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="processing", current_stage="analyzing", progress_percentage=50)
    db.add(analysis)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/cancel",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"

    db.refresh(analysis)
    assert analysis.cancellation_requested is True
    db.close()


def test_cancellation_check_marks_cancelled() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        progress_percentage=40,
        cancellation_requested=True,
    )
    db.add(analysis)
    db.commit()

    cancelled = check_cancellation_requested(db, analysis.id, logger)

    assert cancelled is True
    db.refresh(analysis)
    assert analysis.status == "cancelled"
    db.close()
