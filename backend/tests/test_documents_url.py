from datetime import UTC, datetime

from documents.models import Document
from shared.config import get_settings
from shared.database import SessionLocal
from users.models import User


def _get_test_user_id() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    user_id = str(user.id)
    db.close()
    return user_id


def _create_document(*, created_by: str) -> Document:
    db = SessionLocal()
    document = Document(
        analysis_id="analysis-1",
        filename="Pliego Principal.pdf",
        blob_name="analyses/analysis-1/pliego.pdf",
        file_size_bytes=1200,
        page_count=10,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by=created_by,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    db.close()
    return document


def test_get_document_url_requires_auth(client):
    document = _create_document(created_by=_get_test_user_id())

    response = client.get(f"/api/v1/documents/{document.id}/url")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_AUTH"


def test_get_document_url_not_found(client, auth_token):
    response = client.get(
        "/api/v1/documents/non-existent-id/url",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_get_document_url_returns_sas_payload(client, auth_token, monkeypatch):
    document = _create_document(created_by=_get_test_user_id())

    now = datetime.now(UTC).replace(microsecond=0)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    monkeypatch.setattr("documents.routes.datetime", _FrozenDateTime)
    monkeypatch.setattr("documents.routes.generate_blob_sas", lambda **_: "sv=2021-06-08&sp=r&sig=test")

    class _FakeBlobClient:
        url = "https://account.blob.core.windows.net/documents/analyses/analysis-1/pliego.pdf"

    class _FakeService:
        account_name = "account"

        def get_blob_client(self, container, blob):
            assert container == "documents"
            assert blob == document.blob_name
            return _FakeBlobClient()

    monkeypatch.setenv("AZURE_BLOB_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=account;AccountKey=testkey;EndpointSuffix=core.windows.net")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "documents")
    get_settings.cache_clear()
    monkeypatch.setattr("documents.routes.BlobServiceClient.from_connection_string", lambda _: _FakeService())

    response = client.get(
        f"/api/v1/documents/{document.id}/url",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document.id
    assert payload["filename"] == "Pliego Principal.pdf"
    assert payload["url"].startswith("https://")
    assert "sv=2021-06-08" in payload["url"]

    expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    assert int((expires_at - now).total_seconds()) == 3600


def test_get_document_url_with_sas_only_connection_string(client, auth_token, monkeypatch):
    """Reproduces production config: connection string built from an account-level
    SAS (BlobEndpoint + SharedAccessSignature) instead of an AccountKey."""
    document = _create_document(created_by=_get_test_user_id())

    sas_expiry = "2099-01-01T00:00:00Z"
    sas_query = f"sp=racwdli&st=2024-01-01T00:00:00Z&se={sas_expiry}&spr=https&sv=2022-11-02&sr=c&sig=testsig"

    class _FakeBlobClient:
        # The real SDK bakes the connection string's SharedAccessSignature into
        # the account URL, so blob_client.url already carries it as a query string.
        url = f"https://account.blob.core.windows.net/documents/analyses/analysis-1/pliego.pdf?{sas_query}"

    class _FakeService:
        account_name = "account"

        def get_blob_client(self, container, blob):
            assert container == "documents"
            assert blob == document.blob_name
            return _FakeBlobClient()

    monkeypatch.setenv(
        "AZURE_BLOB_CONNECTION_STRING",
        f"BlobEndpoint=https://account.blob.core.windows.net/;SharedAccessSignature={sas_query}",
    )
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_NAME", "documents")
    get_settings.cache_clear()
    monkeypatch.setattr("documents.routes.BlobServiceClient.from_connection_string", lambda _: _FakeService())

    response = client.get(
        f"/api/v1/documents/{document.id}/url",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == _FakeBlobClient.url
    assert payload["url"].count("sig=testsig") == 1
    assert payload["expires_at"] == sas_expiry
