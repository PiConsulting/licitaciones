"""AC5: borrar un Analysis cascadea a sus events/deadlines vía ON DELETE
CASCADE. SQLite (usado por el resto de la suite) no aplica FKs por default,
así que esto necesita Postgres real -- reusa el patrón de
`tests/indexing/conftest.py` (se salta si no hay Postgres local disponible).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from timeline import repository
from timeline.models import Deadline, Event
from timeline.models_orm import DeadlineORM, EventORM


@pytest.fixture
def pg_seeded_analysis(pg_session_factory):
    import analysis.models as _analysis_models  # noqa: F401
    import users.models as _users_models  # noqa: F401
    from analysis.models import Analysis
    from users.models import User

    db = pg_session_factory()
    user_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())

    db.add(
        User(id=user_id, email=f"{user_id}@cascade-test.local", password_hash="x", name="Cascade Test")
    )
    db.commit()
    db.add(Analysis(id=analysis_id, created_by=user_id))
    db.commit()
    db.close()

    yield analysis_id

    db = pg_session_factory()
    db.execute(text("DELETE FROM analyses WHERE id = :id"), {"id": analysis_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()
    db.close()


def test_deleting_analysis_cascades_to_events_and_deadlines(pg_session_factory, pg_seeded_analysis):
    analysis_id = pg_seeded_analysis
    db = pg_session_factory()

    event = repository.create_event(
        db, Event(partition_key=analysis_id, analysis_id=analysis_id, name="Evento de prueba")
    )
    repository.create_deadline(
        db,
        Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            name="Deadline de prueba",
            duration=3,
            trigger_event_id=event.event_id,
        ),
    )
    db.close()

    db = pg_session_factory()
    assert db.execute(select(EventORM).where(EventORM.analysis_id == analysis_id)).scalars().all()
    assert db.execute(select(DeadlineORM).where(DeadlineORM.analysis_id == analysis_id)).scalars().all()

    db.execute(text("DELETE FROM analyses WHERE id = :id"), {"id": analysis_id})
    db.commit()

    remaining_events = (
        db.execute(select(EventORM).where(EventORM.analysis_id == analysis_id)).scalars().all()
    )
    remaining_deadlines = (
        db.execute(select(DeadlineORM).where(DeadlineORM.analysis_id == analysis_id)).scalars().all()
    )
    db.close()

    assert remaining_events == []
    assert remaining_deadlines == []
