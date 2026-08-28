"""Tests de tracking sobre PostgreSQL/SQLAlchemy (Historia 22.8)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.tracking.service.conftest import OTHER_USER_ID, OWNER_USER_ID
from tracking.models import Tracking
from tracking.schemas import AnalysisTracking
from tracking.schemas import TrackingComment as TrackingCommentSchema
from tracking.service import (
    complete_tracking,
    create_comment,
    delete_comment,
    get_tracking,
    list_comments,
    start_tracking,
    update_category_status,
    update_comment,
    update_tracking_item_status,
)


class TestStartTracking:
    def test_creates_default_checklist_from_extracted_data(self, analyzed_analysis):
        analysis_id, version_id = analyzed_analysis
        tracking = start_tracking(analysis_id, OWNER_USER_ID)

        assert tracking["status"] == "active"
        assert tracking["version_id"] == version_id
        categories_by_key = {c["category_key"]: c for c in tracking["categories"]}
        assert len(categories_by_key["requisitos_admisibilidad"]["items"]) == 2
        assert len(categories_by_key["anexos_obligatorios"]["items"]) == 1
        # categorías no accionables quedan sin items pero presentes (7 total)
        assert len(tracking["categories"]) == 7
        assert categories_by_key["objeto_alcance"]["items"] == []
        assert tracking["summary"]["total_categories"] == 7

    def test_start_twice_returns_same_tracking(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        first = start_tracking(analysis_id, OWNER_USER_ID)
        second = start_tracking(analysis_id, OWNER_USER_ID)
        assert first["id"] == second["id"]

    def test_unanalyzed_analysis_raises(self, db_session):
        from analysis.models import Analysis

        analysis = Analysis(id="draft-analysis", created_by=OWNER_USER_ID, status="draft")
        db_session.add(analysis)
        db_session.commit()

        with pytest.raises(RuntimeError, match="TRACKING_NOT_AVAILABLE"):
            start_tracking(analysis.id, OWNER_USER_ID)

    def test_resume_completed_tracking(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        complete_tracking(analysis_id, OWNER_USER_ID, completed_by_name="Owner")

        resumed = start_tracking(analysis_id, OWNER_USER_ID)
        assert resumed["status"] == "active"


class TestGetTracking:
    def test_returns_none_when_not_started(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        assert get_tracking(analysis_id, OWNER_USER_ID) is None

    def test_wrong_owner_raises_permission_error(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        with pytest.raises(PermissionError):
            get_tracking(analysis_id, OTHER_USER_ID)

    def test_nonexistent_analysis_raises_value_error(self):
        with pytest.raises(ValueError, match="ANALYSIS_NOT_FOUND"):
            get_tracking("does-not-exist", OWNER_USER_ID)


class TestCompleteTracking:
    def test_complete_sets_status_and_resolves_display_name(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        completed = complete_tracking(analysis_id, OWNER_USER_ID)
        assert completed["status"] == "completed"
        assert completed["completed_by_name"] == "Tracking Owner"  # AC5: resuelto desde `users`

    def test_complete_is_idempotent(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        first = complete_tracking(analysis_id, OWNER_USER_ID)
        second = complete_tracking(analysis_id, OWNER_USER_ID)
        assert first["completed_at"] == second["completed_at"]


class TestCategoryStatusTransitions:
    def test_valid_transition_in_review_to_closed(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        updated = update_category_status(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "closed")
        category = next(c for c in updated["categories"] if c["category_key"] == "requisitos_admisibilidad")
        assert category["status"] == "closed"
        assert category["closed_by"] == OWNER_USER_ID

    def test_invalid_transition_raises(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        with pytest.raises(ValueError, match="INVALID_TRACKING_TRANSITION"):
            update_category_status(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "not_reviewed")

    def test_reopen_closed_category(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        update_category_status(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "closed")

        reopened = update_category_status(
            analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "in_review"
        )
        category = next(
            c for c in reopened["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )
        assert category["status"] == "in_review"
        assert category["reopened_by"] == OWNER_USER_ID

    def test_closed_category_blocks_item_update(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        tracking = start_tracking(analysis_id, OWNER_USER_ID)
        item_id = next(
            c for c in tracking["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )["items"][0]["tracking_item_id"]

        update_category_status(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "closed")

        with pytest.raises(RuntimeError, match="TRACKING_CATEGORY_CLOSED"):
            update_tracking_item_status(
                analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", item_id, "compliant"
            )

    def test_unknown_category_raises(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        with pytest.raises(ValueError, match="TRACKING_CATEGORY_NOT_FOUND"):
            update_category_status(analysis_id, OWNER_USER_ID, "categoria_inexistente", "closed")


class TestItemStatusUpdate:
    def test_update_item_status(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        tracking = start_tracking(analysis_id, OWNER_USER_ID)
        item_id = next(
            c for c in tracking["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )["items"][0]["tracking_item_id"]

        updated = update_tracking_item_status(
            analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", item_id, "compliant"
        )
        category = next(
            c for c in updated["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )
        item = next(i for i in category["items"] if i["tracking_item_id"] == item_id)
        assert item["status"] == "compliant"
        assert item["updated_by"] == OWNER_USER_ID

    def test_unknown_item_raises(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        with pytest.raises(ValueError, match="TRACKING_ITEM_NOT_FOUND"):
            update_tracking_item_status(
                analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "no-existe", "compliant"
            )


class TestComments:
    def test_create_list_update_delete_roundtrip(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        created = create_comment(
            analysis_id,
            OWNER_USER_ID,
            "requisitos_admisibilidad",
            scope="category",
            content="Falta el certificado actualizado",
            tracking_item_id=None,
        )
        assert created["created_by_name"] == "Tracking Owner"

        listed = list_comments(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad")
        assert len(listed) == 1
        assert listed[0]["id"] == created["id"]

        updated = update_comment(
            analysis_id,
            OWNER_USER_ID,
            "requisitos_admisibilidad",
            created["id"],
            content="Certificado recibido, pendiente de validar",
        )
        assert updated["content"] == "Certificado recibido, pendiente de validar"
        assert updated["edited_by"] == OWNER_USER_ID

        delete_comment(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", created["id"])
        after_delete = list_comments(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad")
        assert after_delete == []

    def test_item_scope_comment_rejected(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        with pytest.raises(ValueError, match="TRACKING_CATEGORY_COMMENT_ONLY"):
            create_comment(
                analysis_id,
                OWNER_USER_ID,
                "requisitos_admisibilidad",
                scope="checklist_item",
                content="x",
                tracking_item_id="some-item",
            )

    def test_comment_on_closed_category_rejected(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        update_category_status(analysis_id, OWNER_USER_ID, "requisitos_admisibilidad", "closed")

        with pytest.raises(RuntimeError, match="TRACKING_CATEGORY_CLOSED"):
            create_comment(
                analysis_id,
                OWNER_USER_ID,
                "requisitos_admisibilidad",
                scope="category",
                content="x",
                tracking_item_id=None,
            )

    def test_comments_count_reflected_in_tracking_payload(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        create_comment(
            analysis_id,
            OWNER_USER_ID,
            "requisitos_admisibilidad",
            scope="category",
            content="comentario",
            tracking_item_id=None,
        )
        tracking = get_tracking(analysis_id, OWNER_USER_ID)
        category = next(
            c for c in tracking["categories"] if c["category_key"] == "requisitos_admisibilidad"
        )
        assert category["comments_count"] == 1


class TestConcurrencyConflict:
    def test_stale_expected_updated_at_raises_tracking_conflict(self, analyzed_analysis, db_session):
        """AC2/AC3: el equivalente Postgres del ETag mismatch de Cosmos --
        un CAS update con un `updated_at` esperado que ya no coincide con el
        real (otra transacción lo cambió primero) falla con
        TRACKING_CONFLICT, en vez de pisar el cambio ajeno en silencio."""
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        from tracking.service.storage import _apply_tracking_cas_update

        row = db_session.query(Tracking).filter(Tracking.analysis_id == analysis_id).first()
        tracking_id = row.id

        with pytest.raises(RuntimeError, match="TRACKING_CONFLICT"):
            _apply_tracking_cas_update(
                db_session, tracking_id, datetime(2000, 1, 1, tzinfo=UTC), datetime.now(UTC)
            )

    def test_correct_expected_updated_at_succeeds(self, analyzed_analysis, db_session):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)

        from tracking.service.storage import _apply_tracking_cas_update

        row = db_session.query(Tracking).filter(Tracking.analysis_id == analysis_id).first()
        new_updated_at = _apply_tracking_cas_update(db_session, row.id, row.updated_at)
        assert new_updated_at is not None


class TestApiContractUnchanged:
    """AC6: el payload de tracking/comments sigue construyendo los
    Pydantic de schemas.py sin cambios."""

    def test_tracking_payload_matches_pydantic_contract(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        tracking = start_tracking(analysis_id, OWNER_USER_ID)
        validated = AnalysisTracking(**tracking)
        assert validated.analysis_id == analysis_id
        assert len(validated.categories) == 7

    def test_comment_payload_matches_pydantic_contract(self, analyzed_analysis):
        analysis_id, _version_id = analyzed_analysis
        start_tracking(analysis_id, OWNER_USER_ID)
        comment = create_comment(
            analysis_id,
            OWNER_USER_ID,
            "requisitos_admisibilidad",
            scope="category",
            content="x",
            tracking_item_id=None,
        )
        validated = TrackingCommentSchema(**comment)
        assert validated.scope == "category"
