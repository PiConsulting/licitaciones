from datetime import UTC, datetime
from uuid import uuid4

import fitz
from fastapi.testclient import TestClient

from analysis.models import Analysis
from analysis.service import check_duplicates
from documents.models import Document
from documents.service import calculate_content_hash
from shared.database import SessionLocal
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

    existing_analysis = Analysis(created_by=user.id, status="completed", correlation_id=str(uuid4()))
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


def test_start_analysis_returns_duplicate_resolution_payload(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    existing_analysis = Analysis(created_by=user.id, status="completed", correlation_id=str(uuid4()))
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


def test_start_analysis_success_with_analyze_again_decision(client: TestClient, auth_token: str, monkeypatch) -> None:
    from analysis import routes as analysis_routes

    monkeypatch.setattr(analysis_routes, "enqueue_analysis", lambda *_args, **_kwargs: None)

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    existing_analysis = Analysis(created_by=user.id, status="completed", correlation_id=str(uuid4()))
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
