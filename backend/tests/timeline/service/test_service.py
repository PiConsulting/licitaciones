"""Tests de TimelineService contra SQLAlchemy (Historia 22.7)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.timeline.service.conftest import OTHER_USER_ID, TEST_USER_ID
from timeline.models import Deadline, Event
from timeline.service import TimelineService


def _make_event(analysis_id: str, **overrides) -> Event:
    defaults = {"partition_key": analysis_id, "analysis_id": analysis_id, "name": "Apertura de ofertas"}
    defaults.update(overrides)
    return Event(**defaults)


def _make_deadline(analysis_id: str, **overrides) -> Deadline:
    defaults = {
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "name": "Presentación de consultas",
        "duration": 5,
    }
    defaults.update(overrides)
    return Deadline(**defaults)


class TestEventCRUD:
    def test_create_and_get_event(self, db_session, analysis_id):
        service = TimelineService(db_session)
        event = _make_event(analysis_id)

        created = service.create_event(event, TEST_USER_ID)
        fetched = service.get_event(created.event_id, analysis_id, TEST_USER_ID)

        assert fetched is not None
        assert fetched.event_id == created.event_id
        assert fetched.name == "Apertura de ofertas"
        assert fetched.id == f"event::{created.event_id}"

    def test_get_nonexistent_event_returns_none(self, db_session, analysis_id):
        service = TimelineService(db_session)
        assert service.get_event("does-not-exist", analysis_id, TEST_USER_ID) is None

    def test_update_event(self, db_session, analysis_id):
        service = TimelineService(db_session)
        created = service.create_event(_make_event(analysis_id), TEST_USER_ID)

        created.name = "Apertura de ofertas (reprogramada)"
        updated = service.update_event(created, TEST_USER_ID)

        assert updated.name == "Apertura de ofertas (reprogramada)"
        refetched = service.get_event(created.event_id, analysis_id, TEST_USER_ID)
        assert refetched.name == "Apertura de ofertas (reprogramada)"

    def test_soft_delete_event(self, db_session, analysis_id):
        service = TimelineService(db_session)
        created = service.create_event(_make_event(analysis_id), TEST_USER_ID)

        deleted = service.delete_event(created.event_id, analysis_id, TEST_USER_ID)
        assert deleted is True

        # get_event no filtra por deleted (paridad con el comportamiento Cosmos original)
        fetched = service.get_event(created.event_id, analysis_id, TEST_USER_ID)
        assert fetched.deleted is True

    def test_delete_nonexistent_event_returns_false(self, db_session, analysis_id):
        service = TimelineService(db_session)
        assert service.delete_event("does-not-exist", analysis_id, TEST_USER_ID) is False

    def test_list_events_excludes_deleted_by_default(self, db_session, analysis_id):
        service = TimelineService(db_session)
        kept = service.create_event(_make_event(analysis_id, name="Vigente"), TEST_USER_ID)
        removed = service.create_event(_make_event(analysis_id, name="Borrado"), TEST_USER_ID)
        service.delete_event(removed.event_id, analysis_id, TEST_USER_ID)

        active = service.list_events(analysis_id, TEST_USER_ID)
        assert [e.event_id for e in active] == [kept.event_id]

        everything = service.list_events(analysis_id, TEST_USER_ID, include_deleted=True)
        assert len(everything) == 2

    def test_list_events_pagination(self, db_session, analysis_id):
        service = TimelineService(db_session)
        for i in range(5):
            service.create_event(_make_event(analysis_id, name=f"Evento {i}"), TEST_USER_ID)

        page = service.list_events(analysis_id, TEST_USER_ID, limit=2, skip=1)
        assert len(page) == 2

    def test_set_event_hidden(self, db_session, analysis_id):
        """2026-09-01: ocultar/mostrar un evento sin borrarlo (distinto del
        soft-delete). El evento sigue existiendo y `get_event` lo sigue
        devolviendo normalmente -- solo cambia el flag `hidden`."""
        service = TimelineService(db_session)
        created = service.create_event(_make_event(analysis_id), TEST_USER_ID)
        assert created.hidden is False

        hidden = service.set_event_hidden(created.event_id, analysis_id, TEST_USER_ID, hidden=True)
        assert hidden is not None
        assert hidden.hidden is True

        fetched = service.get_event(created.event_id, analysis_id, TEST_USER_ID)
        assert fetched.hidden is True
        assert fetched.deleted is False

        shown = service.set_event_hidden(created.event_id, analysis_id, TEST_USER_ID, hidden=False)
        assert shown.hidden is False

    def test_set_event_hidden_nonexistent_returns_none(self, db_session, analysis_id):
        service = TimelineService(db_session)
        result = service.set_event_hidden("does-not-exist", analysis_id, TEST_USER_ID, hidden=True)
        assert result is None

    def test_list_events_excludes_hidden_by_default(self, db_session, analysis_id):
        service = TimelineService(db_session)
        kept = service.create_event(_make_event(analysis_id, name="Vigente"), TEST_USER_ID)
        hidden_ev = service.create_event(_make_event(analysis_id, name="Fuerza mayor"), TEST_USER_ID)
        service.set_event_hidden(hidden_ev.event_id, analysis_id, TEST_USER_ID, hidden=True)

        active = service.list_events(analysis_id, TEST_USER_ID)
        assert [e.event_id for e in active] == [kept.event_id]

        everything = service.list_events(analysis_id, TEST_USER_ID, include_hidden=True)
        assert len(everything) == 2

    def test_hidden_event_still_usable_as_trigger(self, db_session, analysis_id):
        """El punto central del flag `hidden`: un evento oculto no deja de
        ser un evento real -- sigue pudiendo actuar como disparador de un
        deadline de otro evento, sin ningún tratamiento especial."""
        service = TimelineService(db_session)
        trigger = service.create_event(_make_event(analysis_id, name="Adjudicación"), TEST_USER_ID)
        service.set_event_hidden(trigger.event_id, analysis_id, TEST_USER_ID, hidden=True)

        target = service.create_event(_make_event(analysis_id, name="Entrega"), TEST_USER_ID)
        deadline = service.create_deadline(
            _make_deadline(
                analysis_id,
                trigger_event_id=trigger.event_id,
                target_event_id=target.event_id,
            ),
            TEST_USER_ID,
        )

        fetched = service.get_deadline(deadline.deadline_id, analysis_id, TEST_USER_ID)
        assert fetched.trigger_event_id == trigger.event_id


class TestDeadlineCRUD:
    def test_create_and_get_deadline(self, db_session, analysis_id):
        service = TimelineService(db_session)
        created = service.create_deadline(_make_deadline(analysis_id), TEST_USER_ID)

        fetched = service.get_deadline(created.deadline_id, analysis_id, TEST_USER_ID)
        assert fetched is not None
        assert fetched.duration == 5
        assert fetched.id == f"deadline::{created.deadline_id}"

    def test_deadline_linked_to_events(self, db_session, analysis_id):
        service = TimelineService(db_session)
        trigger = service.create_event(_make_event(analysis_id, name="Publicación"), TEST_USER_ID)
        target = service.create_event(_make_event(analysis_id, name="Cierre consultas"), TEST_USER_ID)

        deadline = service.create_deadline(
            _make_deadline(
                analysis_id,
                trigger_event_id=trigger.event_id,
                target_event_id=target.event_id,
            ),
            TEST_USER_ID,
        )

        fetched = service.get_deadline(deadline.deadline_id, analysis_id, TEST_USER_ID)
        assert fetched.trigger_event_id == trigger.event_id
        assert fetched.target_event_id == target.event_id

    def test_soft_delete_deadline(self, db_session, analysis_id):
        service = TimelineService(db_session)
        created = service.create_deadline(_make_deadline(analysis_id), TEST_USER_ID)

        assert service.delete_deadline(created.deadline_id, analysis_id, TEST_USER_ID) is True
        active = service.list_deadlines(analysis_id, TEST_USER_ID)
        assert active == []


class TestOwnershipValidation:
    def test_wrong_owner_raises_403(self, db_session, analysis_id):
        service = TimelineService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            service.create_event(_make_event(analysis_id), OTHER_USER_ID)
        assert exc_info.value.status_code == 403

    def test_nonexistent_analysis_raises_404(self, db_session):
        service = TimelineService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            service.create_event(_make_event("does-not-exist"), TEST_USER_ID)
        assert exc_info.value.status_code == 404
