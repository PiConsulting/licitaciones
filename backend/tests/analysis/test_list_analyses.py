from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from analysis.models import Analysis, AnalysisVersion
from documents.models import Document
from shared.database import SessionLocal
from users.models import User


def _create_analysis(
    *,
    user_id: str,
    status: str,
    filename: str,
    created_at: datetime,
    current_stage: str = "queued",
    deleted: bool = False,
    extracted_data: dict | None = None,
    progress_percentage: int = 0,
    stage_progress: str | None = None,
) -> Analysis:
    db = SessionLocal()
    analysis = Analysis(
        created_by=user_id,
        status=status,
        current_stage=current_stage,
        correlation_id=str(uuid4()),
        created_at=created_at,
        updated_at=created_at,
        progress_percentage=progress_percentage,
        extraction_metadata={"stage_progress": stage_progress} if stage_progress else {},
        deleted_at=created_at if deleted else None,
    )
    db.add(analysis)
    db.flush()

    doc = Document(
        analysis_id=analysis.id,
        filename=filename,
        blob_name=f"{analysis.id}/{filename}",
        file_size_bytes=100,
        page_count=1,
        is_primary=True,
        sha256_hash=("a" + analysis.id.replace("-", ""))[:64].ljust(64, "0"),
        content_hash=("b" + analysis.id.replace("-", ""))[:64].ljust(64, "0"),
        created_by=user_id,
        uploaded_at=created_at,
    )
    db.add(doc)

    if extracted_data is not None:
        version = AnalysisVersion(
            analysis_id=analysis.id,
            version_number=1,
            extracted_data=extracted_data,
            conflicts=[],
            created_by=user_id,
            created_at=created_at,
        )
        db.add(version)
        db.flush()
        analysis.current_version_id = version.id

    db.commit()
    db.refresh(analysis)
    db.close()
    return analysis


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_analyses_excludes_soft_deleted(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    visible = _create_analysis(user_id=user.id, status="queued", filename="visible.pdf", created_at=now)
    _create_analysis(user_id=user.id, status="queued", filename="deleted.pdf", created_at=now, deleted=True)

    response = client.get("/api/v1/analyses", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == visible.id


def test_list_analyses_filters_by_status(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    _create_analysis(user_id=user.id, status="queued", filename="queued.pdf", created_at=now)
    analyzed = _create_analysis(user_id=user.id, status="analyzed", filename="done.pdf", created_at=now)

    response = client.get("/api/v1/analyses?status=analyzed", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == analyzed.id


def test_list_analyses_filters_by_date_range(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    older = datetime(2026, 7, 20, tzinfo=UTC)
    middle = datetime(2026, 7, 25, tzinfo=UTC)
    newer = datetime(2026, 7, 30, tzinfo=UTC)

    _create_analysis(user_id=user.id, status="queued", filename="old.pdf", created_at=older)
    kept = _create_analysis(user_id=user.id, status="queued", filename="middle.pdf", created_at=middle)
    _create_analysis(user_id=user.id, status="queued", filename="new.pdf", created_at=newer)

    response = client.get(
        "/api/v1/analyses?date_from=2026-07-24&date_to=2026-07-26",
        headers=_auth_headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == kept.id


def test_list_analyses_searches_by_primary_filename(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    matched = _create_analysis(user_id=user.id, status="queued", filename="Pliego Hospital Central.pdf", created_at=now)
    _create_analysis(user_id=user.id, status="queued", filename="Otro documento.pdf", created_at=now)

    response = client.get("/api/v1/analyses?search=hospital", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == matched.id


def test_list_analyses_searches_by_organism(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    matched = _create_analysis(
        user_id=user.id,
        status="analyzed",
        filename="pliego-escuelas.pdf",
        created_at=now,
        extracted_data={
            "datos_procedimiento": {
                "confidence": 0.8,
                "extraction_status": "success",
                "items": [
                    {
                        "field_name": "Organismo convocante",
                        "field_value": "Ministerio de Educación",
                        "field_state": "extraido",
                        "confidence": 0.8,
                        "citations": [],
                    }
                ],
                "summary": "",
                "is_reviewed": False,
                "source_references": [],
            }
        },
    )
    _create_analysis(user_id=user.id, status="analyzed", filename="pliego-vial.pdf", created_at=now)

    response = client.get("/api/v1/analyses?search=ministerio", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == matched.id
    assert payload["items"][0]["organismo"] == "Ministerio de Educación"


def test_list_analyses_pagination_returns_page_window(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    base = datetime.now(UTC)
    for i in range(25):
        _create_analysis(
            user_id=user.id,
            status="queued",
            filename=f"pliego-{i}.pdf",
            created_at=base - timedelta(minutes=i),
        )

    # Probar con per_page=10 explícito (ahora es el default)
    response = client.get("/api/v1/analyses?page=2&per_page=10", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["per_page"] == 10
    assert payload["total"] == 25
    assert payload["total_pages"] == 3  # 25 items / 10 per page = 3 pages
    assert len(payload["items"]) == 10


def test_list_analyses_sorting_toggle_by_status(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    _create_analysis(user_id=user.id, status="queued", filename="queued.pdf", created_at=now)
    _create_analysis(user_id=user.id, status="analyzed", filename="analyzed.pdf", created_at=now)

    asc_response = client.get(
        "/api/v1/analyses?sort_by=status&sort_order=asc",
        headers=_auth_headers(auth_token),
    )
    desc_response = client.get(
        "/api/v1/analyses?sort_by=status&sort_order=desc",
        headers=_auth_headers(auth_token),
    )

    assert asc_response.status_code == 200
    assert desc_response.status_code == 200

    asc_statuses = [item["status"] for item in asc_response.json()["items"]]
    desc_statuses = [item["status"] for item in desc_response.json()["items"]]

    assert asc_statuses == sorted(asc_statuses)
    assert desc_statuses == sorted(desc_statuses, reverse=True)


def test_list_analyses_confidence_avg_uses_only_success_items(client: TestClient, auth_token: str) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    now = datetime.now(UTC)
    analysis = _create_analysis(
        user_id=user.id,
        status="analyzed",
        filename="pliego-confianza.pdf",
        created_at=now,
        extracted_data={
            "objeto_alcance": {"confidence": 0.9, "extraction_status": "success"},
            "plazos_clave": {"confidence": 0.5, "extraction_status": "partial"},
            "garantias": {"confidence": 0.2, "extraction_status": "failed"},
            "anexos": {"confidence": "0.7", "extraction_status": "success"},
            "datos_procedimiento": {"confidence": 0.7, "extraction_status": "success"},
        },
    )

    response = client.get(f"/api/v1/analyses?search={analysis.id}", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["confidence_avg"] == 0.8


def test_list_analyses_default_pagination_is_10_items(client: TestClient, auth_token: str) -> None:
    """Test que el default de per_page es 10 items por página."""
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None
    db.close()

    # Crear 15 análisis para verificar que solo se muestran 10 por defecto
    base = datetime.now(UTC)
    for i in range(15):
        _create_analysis(
            user_id=user.id,
            status="queued",
            filename=f"pliego-{i}.pdf",
            created_at=base - timedelta(minutes=i),
        )

    # Request sin especificar per_page - debe usar el default
    response = client.get("/api/v1/analyses", headers=_auth_headers(auth_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["per_page"] == 10, "El default de per_page debe ser 10"
    assert payload["total"] == 15
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 10, "La primera página debe tener exactamente 10 items"
