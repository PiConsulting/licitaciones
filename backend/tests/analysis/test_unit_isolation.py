from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient

from analysis.models import Analysis
from documents.models import Document
from infra.business_units import BUSINESS_UNITS
from infra.database import SessionLocal
from users.models import User

UNIT_A = BUSINESS_UNITS[0]
UNIT_B = BUSINESS_UNITS[1]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _superadmin_id() -> str:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == "test@cedia.com").one().id


def _analysis(business_unit: str | None, name: str, business_status: str = "en_revision") -> str:
    with SessionLocal() as db:
        analysis = Analysis(
            created_by=_superadmin_id(),
            status="analyzed",
            correlation_id=str(uuid4()),
            business_status=business_status,
            business_unit=business_unit,
            analysis_name=name,
        )
        db.add(analysis)
        db.commit()
        return analysis.id


def _document(analysis_id: str) -> str:
    with SessionLocal() as db:
        document = Document(
            analysis_id=analysis_id,
            filename="pliego.pdf",
            blob_name=f"{analysis_id}/pliego.pdf",
            file_size_bytes=10,
            page_count=1,
            is_primary=True,
            sha256_hash="x",
            content_hash="y",
            created_by=_superadmin_id(),
        )
        db.add(document)
        db.commit()
        return document.id


def _pdf() -> bytes:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    try:
        return doc.tobytes()
    finally:
        doc.close()


class _FakeStorage:
    def upload(self, blob_name: str, content: bytes) -> None:
        return None

    def delete(self, blob_name: str) -> None:
        return None


@pytest.fixture
def two_units():
    return _analysis(UNIT_A, "Pliego A"), _analysis(UNIT_B, "Pliego B")


@pytest.fixture
def fake_storage(monkeypatch):
    monkeypatch.setattr("analysis.service.upload._build_blob_storage", lambda: _FakeStorage())


def _names(response) -> set[str]:
    return {item["analysis_name"] for item in response.json()["items"]}


def test_member_lists_only_own_unit(client: TestClient, member_token: str, two_units):
    response = client.get("/api/v1/analyses", headers=_headers(member_token))

    assert response.status_code == 200
    assert _names(response) == {"Pliego A"}
    assert response.json()["total"] == 1


def test_member_cannot_widen_scope_with_unit_filter(
    client: TestClient, member_token: str, two_units
):
    response = client.get(
        f"/api/v1/analyses?business_unit={UNIT_B}", headers=_headers(member_token)
    )

    assert response.json()["items"] == []


def test_member_search_does_not_leak_other_units(
    client: TestClient, member_token: str, two_units
):
    response = client.get("/api/v1/analyses?search=Pliego", headers=_headers(member_token))

    assert _names(response) == {"Pliego A"}


def test_superadmin_sees_all_units_and_can_filter(client: TestClient, auth_token: str, two_units):
    everything = client.get("/api/v1/analyses", headers=_headers(auth_token))
    only_b = client.get(f"/api/v1/analyses?business_unit={UNIT_B}", headers=_headers(auth_token))

    assert _names(everything) == {"Pliego A", "Pliego B"}
    assert _names(only_b) == {"Pliego B"}


def test_member_analysis_of_other_unit_is_not_found(
    client: TestClient, member_token: str, two_units
):
    analysis_a, analysis_b = two_units

    own = client.get(f"/api/v1/analyses/{analysis_a}/status", headers=_headers(member_token))
    other = client.get(f"/api/v1/analyses/{analysis_b}/status", headers=_headers(member_token))

    assert own.status_code == 200
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_superadmin_reads_any_unit(client: TestClient, auth_token: str, two_units):
    for analysis_id in two_units:
        assert (
            client.get(
                f"/api/v1/analyses/{analysis_id}/status", headers=_headers(auth_token)
            ).status_code
            == 200
        )


def test_member_mutations_on_other_unit_are_not_found(
    client: TestClient, member_token: str, two_units
):
    _, analysis_b = two_units
    headers = _headers(member_token)

    assert client.get(f"/api/v1/analyses/{analysis_b}/status", headers=headers).status_code == 404
    assert client.delete(f"/api/v1/analyses/{analysis_b}", headers=headers).status_code == 404
    assert client.post(f"/api/v1/analyses/{analysis_b}/cancel", headers=headers).status_code == 404


def test_member_tracking_and_timeline_of_other_unit_are_not_found(
    client: TestClient, member_token: str, two_units
):
    _, analysis_b = two_units
    headers = _headers(member_token)

    assert client.get(f"/api/v1/analyses/{analysis_b}/tracking", headers=headers).status_code == 404
    assert (
        client.get(f"/api/v1/analyses/{analysis_b}/deadlines", headers=headers).status_code == 404
    )


def test_member_document_of_other_unit_is_not_found(
    client: TestClient, member_token: str, two_units
):
    analysis_a, analysis_b = two_units
    document_a = _document(analysis_a)
    document_b = _document(analysis_b)
    headers = _headers(member_token)

    assert client.get(f"/api/v1/documents/{document_b}/url", headers=headers).status_code == 404
    assert client.get(f"/api/v1/documents/{document_a}/url", headers=headers).status_code != 404


def test_member_summary_counts_only_own_unit(client: TestClient, member_token: str, two_units):
    response = client.get("/api/v1/analyses/business-status-summary", headers=_headers(member_token))

    assert response.json()["total"] == 1


def test_superadmin_summary_counts_every_unit(client: TestClient, auth_token: str, two_units):
    response = client.get("/api/v1/analyses/business-status-summary", headers=_headers(auth_token))

    assert response.json()["total"] == 2


def test_units_endpoint_limits_member_to_own_unit(
    client: TestClient, member_token: str, auth_token: str, two_units
):
    member = client.get("/api/v1/analyses/units", headers=_headers(member_token)).json()
    admin = client.get("/api/v1/analyses/units", headers=_headers(auth_token)).json()

    assert [item["business_unit"] for item in member] == [UNIT_A]
    assert [item["business_unit"] for item in admin] == list(BUSINESS_UNITS)


def test_member_does_not_see_upcoming_events_of_other_units(
    client: TestClient, member_token: str, two_units
):
    response = client.get("/api/v1/analyses/upcoming-events", headers=_headers(member_token))

    assert response.status_code == 200
    assert response.json() == []


def test_member_upload_uses_own_unit_and_ignores_requested_one(
    client: TestClient, member_token: str, fake_storage
):
    response = client.post(
        "/api/v1/analyses",
        headers=_headers(member_token),
        data={"primary_file_index": "0", "business_unit": UNIT_B},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )

    assert response.status_code == 201
    with SessionLocal() as db:
        assert db.get(Analysis, response.json()["id"]).business_unit == UNIT_A


def test_member_upload_without_unit_field_uses_own_unit(
    client: TestClient, other_unit_member_token: str, fake_storage
):
    response = client.post(
        "/api/v1/analyses",
        headers=_headers(other_unit_member_token),
        data={"primary_file_index": "0"},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )

    assert response.status_code == 201
    with SessionLocal() as db:
        assert db.get(Analysis, response.json()["id"]).business_unit == UNIT_B


def test_superadmin_upload_uses_chosen_unit(client: TestClient, auth_token: str, fake_storage):
    response = client.post(
        "/api/v1/analyses",
        headers=_headers(auth_token),
        data={"primary_file_index": "0", "business_unit": UNIT_B.lower()},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )

    assert response.status_code == 201
    with SessionLocal() as db:
        assert db.get(Analysis, response.json()["id"]).business_unit == UNIT_B


def test_superadmin_upload_requires_valid_unit(client: TestClient, auth_token: str, fake_storage):
    missing = client.post(
        "/api/v1/analyses",
        headers=_headers(auth_token),
        data={"primary_file_index": "0"},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )
    invalid = client.post(
        "/api/v1/analyses",
        headers=_headers(auth_token),
        data={"primary_file_index": "0", "business_unit": "Inexistente"},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "BUSINESS_UNIT_REQUIRED"
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "BUSINESS_UNIT_INVALID"


def test_member_without_unit_cannot_upload(client: TestClient, fake_storage):
    from users.service import create_access_token, get_password_hash

    with SessionLocal() as db:
        user = User(
            email="sin-unidad@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Sin Unidad",
        )
        db.add(user)
        db.commit()
        token = create_access_token(user.id)

    response = client.post(
        "/api/v1/analyses",
        headers=_headers(token),
        data={"primary_file_index": "0"},
        files=[("files", ("a.pdf", _pdf(), "application/pdf"))],
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_WITHOUT_BUSINESS_UNIT"
    assert client.get("/api/v1/analyses", headers=_headers(token)).json()["items"] == []
