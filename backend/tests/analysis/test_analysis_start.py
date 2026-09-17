from datetime import UTC, datetime
from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient

from analysis.models import Analysis, AnalysisVersion, CurrentStage
from analysis.progress import build_stage_progress
from analysis.service import check_duplicates
from analysis.service.lifecycle import _run_reanalysis, _run_selected_categories_reanalysis
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


def test_reanalyze_endpoint_validates_type_and_payload(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()

    invalid_type_response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "unknown", "categories": []},
    )
    assert invalid_type_response.status_code == 422

    empty_categories_response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "categories", "categories": []},
    )
    assert empty_categories_response.status_code == 400
    assert empty_categories_response.json()["error"]["code"] == "REANALYZE_CATEGORIES_REQUIRED"

    invalid_categories_response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "categories", "categories": ["no_existe"]},
    )
    assert invalid_categories_response.status_code == 400
    assert invalid_categories_response.json()["error"]["code"] == "REANALYZE_CATEGORIES_INVALID"
    db.close()


def test_reanalyze_endpoint_ownership_guard(client: TestClient, auth_token: str) -> None:
    other_user = _create_other_user()
    analysis = _create_user_analysis(other_user.id, status="analyzed")

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "all", "categories": []},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_reanalyze_endpoint_enqueues_background_task(
    client: TestClient, auth_token: str, monkeypatch
) -> None:
    from analysis import routes as analysis_routes

    queued: list[tuple[str, str, list[str]]] = []
    monkeypatch.setattr(
        analysis_routes,
        "enqueue_reanalyze",
        lambda _background_tasks, analysis_id, reanalysis_type, categories: queued.append(
            (analysis_id, reanalysis_type, categories)
        ),
    )

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "phase1", "categories": []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["reanalysis_type"] == "phase1"
    assert payload["source_version_id"] is None
    assert payload["target_version_id"] is None
    assert queued == [
        (
            analysis.id,
            "phase1",
            [
                "preview_criterios",
                "objeto_alcance",
                "identificacion_procedimiento",
                "requisitos_admisibilidad",
                "plazos_clave",
                "garantias",
                "riesgos",
            ],
        )
    ]

    db.refresh(analysis)
    assert analysis.status == "queued"
    assert (analysis.extraction_metadata or {}).get("reanalysis_type") == "phase1"
    db.close()


def test_reanalyze_endpoint_rejects_invalid_status(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="processing", correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "all", "categories": []},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ANALYSIS_REANALYZE_NOT_ALLOWED"
    db.close()


def test_reanalyze_endpoint_rejects_empty_or_invalid_categories(
    client: TestClient, auth_token: str
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()

    empty_response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "categories", "categories": []},
    )
    assert empty_response.status_code == 400
    assert empty_response.json()["error"]["code"] == "REANALYZE_CATEGORIES_REQUIRED"

    invalid_response = client.post(
        f"/api/v1/analyses/{analysis.id}/reanalyze",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"reanalysis_type": "categories", "categories": ["invalida"]},
    )
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "REANALYZE_CATEGORIES_INVALID"
    db.close()


def test_reanalyze_phase2_creates_new_version_and_preserves_previous(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "objeto_alcance": [{"valor": "Objeto base"}],
            "causales_rechazo": [{"valor": "Causal vieja"}],
        },
        conflicts=[{"a": 1}],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()
    source_id = source.id

    def _fake_phase2(analysis_id: str) -> None:
        inner = SessionLocal()
        try:
            local_analysis = inner.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert local_analysis is not None
            current = (
                inner.query(AnalysisVersion)
                .filter(AnalysisVersion.id == local_analysis.current_version_id)
                .first()
            )
            assert current is not None
            payload = dict(current.extracted_data or {})
            payload["causales_rechazo"] = [{"valor": "Causal nueva"}]
            current.extracted_data = payload
            local_analysis.status = "analyzed"
            inner.commit()
        finally:
            inner.close()

    monkeypatch.setattr("analysis.service.lifecycle.extract_and_index_phase2", _fake_phase2)

    _run_reanalysis(analysis.id, "phase2", [])

    db.refresh(analysis)
    current = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    previous = db.query(AnalysisVersion).filter(AnalysisVersion.id == source_id).first()

    assert current is not None
    assert previous is not None
    assert current.id != source_id
    assert current.version_number == 2
    assert previous.extracted_data["causales_rechazo"][0]["valor"] == "Causal vieja"
    assert current.extracted_data["causales_rechazo"][0]["valor"] == "Causal nueva"
    assert current.extracted_data["objeto_alcance"][0]["valor"] == "Objeto base"
    db.close()


def test_reanalyze_phase1_creates_new_full_version(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "objeto_alcance": [{"valor": "Objeto viejo"}],
            "criterios_evaluacion": [{"valor": "Criterio previo"}],
        },
        conflicts=[{"legacy": True}],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()

    def _fake_extract_categories_phase1(inner_db, local_analysis, *, total_nodes: int) -> None:
        assert total_nodes >= 1
        new_version = AnalysisVersion(
            analysis_id=local_analysis.id,
            version_number=2,
            extracted_data={"objeto_alcance": [{"valor": "Objeto reanalizado"}]},
            conflicts=[{"new": True}],
            created_by=local_analysis.created_by,
        )
        inner_db.add(new_version)
        inner_db.flush()
        local_analysis.current_version_id = new_version.id
        local_analysis.status = "en_revision"
        inner_db.commit()

    monkeypatch.setattr(
        "analysis.service.lifecycle.extract_categories_phase1",
        _fake_extract_categories_phase1,
    )

    _run_reanalysis(analysis.id, "phase1", [])

    db.refresh(analysis)
    current = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    assert current is not None
    assert analysis.status == "analyzed"
    assert current.version_number == 2
    assert current.extracted_data["objeto_alcance"][0]["valor"] == "Objeto reanalizado"
    assert current.extracted_data["criterios_evaluacion"][0]["valor"] == "Criterio previo"
    db.close()


def test_reanalyze_all_creates_new_version(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={"objeto_alcance": [{"valor": "Objeto base"}]},
        conflicts=[],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()
    source_id = source.id

    def _fake_phase1(analysis_id: str) -> None:
        inner = SessionLocal()
        try:
            local_analysis = inner.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert local_analysis is not None
            version = AnalysisVersion(
                analysis_id=analysis_id,
                version_number=2,
                extracted_data={"objeto_alcance": [{"valor": "Objeto nuevo"}]},
                conflicts=[],
                created_by=local_analysis.created_by,
            )
            inner.add(version)
            inner.flush()
            local_analysis.current_version_id = version.id
            local_analysis.status = "en_revision"
            inner.commit()
        finally:
            inner.close()

    def _fake_phase2(analysis_id: str) -> None:
        inner = SessionLocal()
        try:
            local_analysis = inner.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert local_analysis is not None
            version = (
                inner.query(AnalysisVersion)
                .filter(AnalysisVersion.id == local_analysis.current_version_id)
                .first()
            )
            assert version is not None
            payload = dict(version.extracted_data or {})
            payload["causales_rechazo"] = [{"valor": "Causal nueva"}]
            version.extracted_data = payload
            local_analysis.status = "analyzed"
            inner.commit()
        finally:
            inner.close()

    monkeypatch.setattr("analysis.service.lifecycle.extract_and_index_phase1", _fake_phase1)
    monkeypatch.setattr("analysis.service.lifecycle.extract_and_index_phase2", _fake_phase2)

    _run_reanalysis(analysis.id, "all", [])

    db.refresh(analysis)
    current = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    previous = db.query(AnalysisVersion).filter(AnalysisVersion.id == source_id).first()

    assert current is not None
    assert previous is not None
    assert current.id != source_id
    assert current.version_number == 2
    assert current.extracted_data["objeto_alcance"][0]["valor"] == "Objeto nuevo"
    assert current.extracted_data["causales_rechazo"][0]["valor"] == "Causal nueva"
    assert previous.extracted_data == {"objeto_alcance": [{"valor": "Objeto base"}]}
    db.close()


def test_reanalyze_categories_preserves_non_selected_categories(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "objeto_alcance": [{"valor": "Objeto original"}],
            "causales_rechazo": [{"valor": "Causal original"}],
            "calidad_por_categoria": {
                "objeto_alcance": {"valid_items": 1},
                "causales_rechazo": {"valid_items": 1},
            },
        },
        conflicts=[{"category": "objeto_alcance", "msg": "old"}],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()
    source_id = source.id

    def _fake_selected_reanalysis(analysis_id: str, selected_categories: list[str]) -> None:
        assert selected_categories == ["causales_rechazo"]
        inner = SessionLocal()
        try:
            local_analysis = inner.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert local_analysis is not None
            version = (
                inner.query(AnalysisVersion)
                .filter(AnalysisVersion.id == local_analysis.current_version_id)
                .first()
            )
            assert version is not None
            payload = dict(version.extracted_data or {})
            payload["causales_rechazo"] = [{"valor": "Causal recalculada"}]
            payload["calidad_por_categoria"] = {
                **dict(payload.get("calidad_por_categoria") or {}),
                "causales_rechazo": {"valid_items": 3},
            }
            version.extracted_data = payload
            version.conflicts = [
                {"category": "objeto_alcance", "msg": "new"},
                {"category": "causales_rechazo", "msg": "new"},
            ]
            local_analysis.status = "analyzed"
            inner.commit()
        finally:
            inner.close()

    monkeypatch.setattr(
        "analysis.service.lifecycle._run_selected_categories_reanalysis",
        _fake_selected_reanalysis,
    )

    _run_reanalysis(analysis.id, "categories", ["causales_rechazo"])

    db.refresh(analysis)
    current = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    previous = db.query(AnalysisVersion).filter(AnalysisVersion.id == source_id).first()

    assert current is not None
    assert previous is not None
    assert current.id != source_id
    assert current.extracted_data["objeto_alcance"][0]["valor"] == "Objeto original"
    assert current.extracted_data["causales_rechazo"][0]["valor"] == "Causal recalculada"
    assert current.extracted_data["calidad_por_categoria"]["objeto_alcance"]["valid_items"] == 1
    assert current.extracted_data["calidad_por_categoria"]["causales_rechazo"]["valid_items"] == 3
    assert previous.extracted_data["causales_rechazo"][0]["valor"] == "Causal original"
    db.close()


def test_reanalyze_preview_criterios_alone_seeds_source_categories(monkeypatch) -> None:
    """Regresión (2026-09-11): reanalizar `preview_criterios` solo, sin sus 4
    categorías fuente en el mismo batch, no debe perder `garantias`/`plazos`/
    `requisitos_admisibilidad`/`riesgos` -- ver comentario en
    `_PREVIEW_CRITERIOS_SOURCE_STATE_KEYS` de `analysis/service/lifecycle.py`."""
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "garantias": [{"tipo": "mantenimiento_oferta", "valor": "1% del monto"}],
            "plazos": [
                {
                    "referencia": "Mantenimiento de oferta",
                    "texto_original": "Las ofertas deberan ser mantenidas por 60 dias",
                }
            ],
            "requisitos_admisibilidad": [{"valor": "ISO 9001"}],
            "riesgos": [{"valor": "riesgo cambiario"}],
            "preview_criterios": [
                {"tipo": "mantenimiento_oferta", "extraction_status": "success", "valor": "60 dias"}
            ],
        },
        conflicts=[],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()
    analysis_id = analysis.id

    captured_state: dict = {}

    class _FakeGraph:
        def invoke(self, state, config=None):
            captured_state.update(state)
            return {"extracted_data": {}, "conflicts": [], "extraction_metadata": {}}

    def _fake_build_single_category_graph(node_name: str, extractor_fn) -> _FakeGraph:
        assert node_name == "extract_preview_criterios"
        return _FakeGraph()

    monkeypatch.setattr(
        "analysis.service.lifecycle._build_single_category_graph",
        _fake_build_single_category_graph,
    )

    _run_selected_categories_reanalysis(analysis_id, ["preview_criterios"])

    assert captured_state.get("garantias") == [
        {"tipo": "mantenimiento_oferta", "valor": "1% del monto"}
    ]
    assert captured_state.get("plazos") == [
        {
            "referencia": "Mantenimiento de oferta",
            "texto_original": "Las ofertas deberan ser mantenidas por 60 dias",
        }
    ]
    assert captured_state.get("requisitos_admisibilidad") == [{"valor": "ISO 9001"}]
    assert captured_state.get("riesgos") == [{"valor": "riesgo cambiario"}]

    db.close()


def test_reanalyze_categories_phase2_only_skips_phase1(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "objeto_alcance": [{"valor": "Objeto original"}],
            "causales_rechazo": [{"valor": "Causal original"}],
        },
        conflicts=[],
        created_by=user.id,
    )
    db.add(source)
    db.flush()
    analysis.current_version_id = source.id
    db.commit()

    phase2_called = False
    selected_helper_called = False

    def _fake_phase2(analysis_id: str) -> None:
        nonlocal phase2_called
        phase2_called = True

    def _fake_selected_reanalysis(analysis_id: str, selected_categories: list[str]) -> None:
        nonlocal selected_helper_called
        selected_helper_called = True
        assert selected_categories == ["causales_rechazo"]
        inner = SessionLocal()
        try:
            local_analysis = inner.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert local_analysis is not None
            version = (
                inner.query(AnalysisVersion)
                .filter(AnalysisVersion.id == local_analysis.current_version_id)
                .first()
            )
            assert version is not None
            payload = dict(version.extracted_data or {})
            payload["causales_rechazo"] = [{"valor": "Causal recalculada"}]
            version.extracted_data = payload
            local_analysis.status = "analyzed"
            inner.commit()
        finally:
            inner.close()

    monkeypatch.setattr("analysis.service.lifecycle.extract_and_index_phase2", _fake_phase2)
    monkeypatch.setattr(
        "analysis.service.lifecycle._run_selected_categories_reanalysis",
        _fake_selected_reanalysis,
    )

    _run_reanalysis(analysis.id, "categories", ["causales_rechazo"])

    db.refresh(analysis)
    current = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )

    assert phase2_called is False
    assert selected_helper_called is True
    assert current is not None
    assert current.version_number == 2
    assert current.extracted_data["objeto_alcance"][0]["valor"] == "Objeto original"
    assert current.extracted_data["causales_rechazo"][0]["valor"] == "Causal recalculada"
    db.close()
