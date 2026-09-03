from datetime import UTC, datetime
from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient

from analysis.models import Analysis, AnalysisVersion, CurrentStage
from analysis.progress import build_stage_progress
from analysis.service import check_duplicates
from documents.models import Document
from documents.service import calculate_content_hash
from infra.database import SessionLocal
from users.models import User
from users.service import create_access_token, get_password_hash


def _build_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _create_other_user() -> User:
    db = SessionLocal()
    user = User(
        email="other@cedia.com",
        password_hash=get_password_hash("Test1234!"),
        name="Other User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _create_user_analysis(user_id: str, status: str = "draft") -> Analysis:
    db = SessionLocal()
    analysis = Analysis(created_by=user_id, status=status, correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    db.close()
    return analysis


def test_check_duplicates_found() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    existing_analysis = Analysis(
        created_by=user.id, status="completed", correlation_id=str(uuid4())
    )
    db.add(existing_analysis)
    db.flush()

    duplicate_hash = "dup-hash-123"
    document = Document(
        analysis_id=existing_analysis.id,
        filename="pliego.pdf",
        blob_name="x/pliego.pdf",
        file_size_bytes=100,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash=duplicate_hash,
        created_by=user.id,
    )
    db.add(document)
    db.commit()

    duplicate = check_duplicates(db, duplicate_hash, user_id=user.id)
    assert duplicate is not None
    assert duplicate["analysis_id"] == existing_analysis.id
    assert duplicate["filename"] == "pliego.pdf"

    db.close()


def test_start_analysis_returns_duplicate_resolution_payload(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    existing_analysis = Analysis(
        created_by=user.id, status="completed", correlation_id=str(uuid4())
    )
    new_analysis = Analysis(created_by=user.id, status="draft", correlation_id=str(uuid4()))
    db.add(existing_analysis)
    db.add(new_analysis)
    db.flush()

    duplicate_hash = "dup-hash-456"
    db.add(
        Document(
            analysis_id=existing_analysis.id,
            filename="existente.pdf",
            blob_name="a/existente.pdf",
            file_size_bytes=100,
            page_count=1,
            is_primary=True,
            sha256_hash="b" * 64,
            content_hash=duplicate_hash,
            created_by=user.id,
        )
    )
    db.add(
        Document(
            analysis_id=new_analysis.id,
            filename="nuevo.pdf",
            blob_name="b/nuevo.pdf",
            file_size_bytes=100,
            page_count=1,
            is_primary=True,
            sha256_hash="c" * 64,
            content_hash=duplicate_hash,
            created_by=user.id,
        )
    )
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{new_analysis.id}/start",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_resolution"] is True
    assert len(payload["duplicates"]) == 1
    assert payload["duplicates"][0]["existing_analysis_id"] == existing_analysis.id

    db.close()


def test_start_analysis_success_with_analyze_again_decision(
    client: TestClient, auth_token: str, monkeypatch
) -> None:
    from analysis import routes as analysis_routes

    monkeypatch.setattr(analysis_routes, "enqueue_analysis", lambda *_args, **_kwargs: None)

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    existing_analysis = Analysis(
        created_by=user.id, status="completed", correlation_id=str(uuid4())
    )
    new_analysis = Analysis(created_by=user.id, status="draft", correlation_id=str(uuid4()))
    db.add(existing_analysis)
    db.add(new_analysis)
    db.flush()

    duplicate_hash = "dup-hash-789"
    db.add(
        Document(
            analysis_id=existing_analysis.id,
            filename="existente.pdf",
            blob_name="a/existente.pdf",
            file_size_bytes=100,
            page_count=1,
            is_primary=True,
            sha256_hash="d" * 64,
            content_hash=duplicate_hash,
            created_by=user.id,
        )
    )
    duplicate_doc = Document(
        analysis_id=new_analysis.id,
        filename="nuevo.pdf",
        blob_name="b/nuevo.pdf",
        file_size_bytes=100,
        page_count=1,
        is_primary=True,
        sha256_hash="e" * 64,
        content_hash=duplicate_hash,
        created_by=user.id,
    )
    db.add(duplicate_doc)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{new_analysis.id}/start",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "decisions": [
                {
                    "document_id": duplicate_doc.id,
                    "action": "analyze_again",
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"

    db.refresh(new_analysis)
    assert new_analysis.status == "queued"
    assert new_analysis.current_stage == "queued"
    db.close()


def test_start_analysis_forbidden_for_other_user(client: TestClient, auth_token: str) -> None:
    other_user = _create_other_user()
    analysis = _create_user_analysis(other_user.id, status="draft")

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/start",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={},
    )

    assert response.status_code == 403
    assert "permisos" in response.json()["error"]["message"]


def test_calculate_content_hash_is_stable_for_same_content() -> None:
    pdf_bytes = _build_pdf()
    hash_a = calculate_content_hash(pdf_bytes)
    hash_b = calculate_content_hash(pdf_bytes)

    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_start_status_endpoint(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        progress_percentage=45,
        correlation_id=str(uuid4()),
        updated_at=datetime.now(UTC),
    )
    db.add(analysis)
    db.commit()

    response = client.get(
        f"/api/v1/analyses/{analysis.id}/status",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["current_stage"] == "analyzing"
    assert payload["progress_percentage"] == 45

    db.close()


def test_get_analysis_detail_legacy_without_preview_criterios(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="analyzed",
        current_stage="completed",
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.flush()

    version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "objeto_alcance": {
                "items": [],
                "confidence": 0,
                "source_references": [],
                "extraction_status": "not_found",
                "summary": "",
                "is_reviewed": False,
            },
            "requisitos_admisibilidad": {
                "items": [],
                "confidence": 0,
                "source_references": [],
                "extraction_status": "not_found",
                "summary": "",
                "is_reviewed": False,
            },
        },
        conflicts=[],
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    analysis.current_version_id = version.id
    db.commit()

    response = client.get(
        f"/api/v1/analyses/{analysis.id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "analyzed"
    assert "preview_criterios" not in payload["current_version"]["extracted_data"]

    db.close()


def test_delete_error_analysis_hard_deletes_records(
    client: TestClient, auth_token: str, monkeypatch
) -> None:
    deleted_blobs: list[str] = []
    deleted_indexes: list[str] = []

    class _FakeBlobStorage:
        def delete(self, blob_name: str) -> None:
            deleted_blobs.append(blob_name)

    monkeypatch.setattr("analysis.service.lifecycle._build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        "analysis.service.lifecycle.delete_analysis_chunks",
        lambda analysis_id: deleted_indexes.append(analysis_id),
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="error", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()
    db.add(
        Document(
            analysis_id=analysis.id,
            filename="fallido.pdf",
            blob_name=f"{analysis.id}/fallido.pdf",
            file_size_bytes=100,
            page_count=1,
            is_primary=True,
            sha256_hash="f" * 64,
            content_hash="hash-error",
            created_by=user.id,
        )
    )
    analysis_id = analysis.id
    db.commit()
    db.close()

    response = client.delete(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 204
    assert deleted_blobs == [f"{analysis_id}/fallido.pdf"]
    assert deleted_indexes == [analysis_id]

    db = SessionLocal()
    assert db.query(Analysis).filter(Analysis.id == analysis_id).first() is None
    assert db.query(Document).filter(Document.analysis_id == analysis_id).count() == 0
    db.close()


def test_delete_completed_analysis_soft_deletes_records(
    client: TestClient, auth_token: str, monkeypatch
) -> None:
    deleted_indexes: list[str] = []
    monkeypatch.setattr(
        "analysis.service.lifecycle.delete_analysis_chunks",
        lambda analysis_id: deleted_indexes.append(analysis_id),
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="completed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()
    document = Document(
        analysis_id=analysis.id,
        filename="ok.pdf",
        blob_name=f"{analysis.id}/ok.pdf",
        file_size_bytes=100,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="hash-completed",
        created_by=user.id,
    )
    db.add(document)
    db.flush()
    analysis_id = analysis.id
    document_id = document.id
    db.commit()
    db.close()

    response = client.delete(
        f"/api/v1/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 204
    assert deleted_indexes == []

    db = SessionLocal()
    stored_analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    stored_document = db.query(Document).filter(Document.id == document_id).first()
    assert stored_analysis is not None
    assert stored_analysis.deleted_at is not None
    assert stored_document is not None
    assert stored_document.deleted_at is not None
    db.close()


@pytest.mark.parametrize("current_status", ["draft", "processing", "queued", "analyzed", "error", "cancelled"])
def test_start_categories_rejects_non_review_status(
    client: TestClient,
    auth_token: str,
    current_status: str,
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status=current_status, correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/start-categories",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "ANALYSIS_NOT_IN_REVIEW"
    db.close()


def test_start_categories_enqueues_phase2(client: TestClient, auth_token: str, monkeypatch) -> None:
    from analysis import routes as analysis_routes

    queued_ids: list[str] = []
    monkeypatch.setattr(
        analysis_routes,
        "enqueue_analysis_categories",
        lambda _background_tasks, analysis_id: queued_ids.append(analysis_id),
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/start-categories",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert queued_ids == [analysis.id]

    db.refresh(analysis)
    assert analysis.progress_percentage == 0
    assert (analysis.extraction_metadata or {}).get("stage_progress") == "En cola"
    db.close()


def test_start_categories_returns_conflict_when_already_transitioned(
    client: TestClient, auth_token: str, monkeypatch
) -> None:
    from analysis import routes as analysis_routes

    queued_ids: list[str] = []
    monkeypatch.setattr(
        analysis_routes,
        "enqueue_analysis_categories",
        lambda _background_tasks, analysis_id: queued_ids.append(analysis_id),
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="queued",
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.commit()
    analysis_id = analysis.id
    db.close()

    class _StaleAnalysis:
        def __init__(self, analysis_id: str) -> None:
            self.id = analysis_id
            self.status = "en_revision"
            self.extraction_metadata = {}

    monkeypatch.setattr(
        analysis_routes,
        "validate_analysis_ownership",
        lambda *_args, **_kwargs: _StaleAnalysis(analysis_id),
    )

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/start-categories",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "ANALYSIS_CATEGORIES_ALREADY_STARTED"
    assert queued_ids == []


def test_build_stage_progress_phase1_no_hardcoded_ocho() -> None:
    message = build_stage_progress(CurrentStage.ANALYZING, done=0, total=3)
    assert "de 8" not in message
