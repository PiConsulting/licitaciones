from io import BytesIO

from fastapi.testclient import TestClient
import pypdf


def _build_pdf(pages: int, encrypted: bool = False) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
      writer.add_blank_page(width=200, height=200)
    if encrypted:
      writer.encrypt(user_password="secret", owner_password="secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_upload_single_pdf_success(client: TestClient, auth_token: str):
    pdf_bytes = _build_pdf(1)

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "0"},
      files=[("files", ("single.pdf", pdf_bytes, "application/pdf"))],
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "draft"
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["is_primary"] is True


def test_upload_multiple_pdfs_manual_primary(client: TestClient, auth_token: str):
    files = [
      ("files", ("first.pdf", _build_pdf(1), "application/pdf")),
      ("files", ("second.pdf", _build_pdf(2), "application/pdf")),
    ]

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "1"},
      files=files,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["documents"][0]["is_primary"] is False
    assert payload["documents"][1]["is_primary"] is True


def test_upload_corrupted_pdf(client: TestClient, auth_token: str):
    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "0"},
      files=[("files", ("corrupted.pdf", b"not-a-pdf", "application/pdf"))],
    )

    assert response.status_code == 400
    assert "está dañado" in response.json()["error"]["message"]


def test_upload_password_protected_pdf(client: TestClient, auth_token: str):
    protected_pdf = _build_pdf(1, encrypted=True)

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "0"},
      files=[("files", ("protected.pdf", protected_pdf, "application/pdf"))],
    )

    assert response.status_code == 400
    assert "protegido con contraseña" in response.json()["error"]["message"]


def test_upload_over_300_pages(client: TestClient, auth_token: str):
    large_pdf = _build_pdf(301)

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "0"},
      files=[("files", ("too-long.pdf", large_pdf, "application/pdf"))],
    )

    assert response.status_code == 400
    assert "máximo es 300" in response.json()["error"]["message"]


def test_upload_large_document_warning(client: TestClient, auth_token: str):
    warning_pdf = _build_pdf(120)

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "0"},
      files=[("files", ("long.pdf", warning_pdf, "application/pdf"))],
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["warnings"]) == 1
    assert "puede demorar" in payload["warnings"][0]["message"]


def test_upload_requires_primary_for_multiple_files(client: TestClient, auth_token: str):
    files = [
      ("files", ("first.pdf", _build_pdf(1), "application/pdf")),
      ("files", ("second.pdf", _build_pdf(1), "application/pdf")),
    ]

    response = client.post(
      "/api/v1/analyses",
      headers={"Authorization": f"Bearer {auth_token}"},
      data={"primary_file_index": "-1"},
      files=files,
    )

    assert response.status_code == 400
    assert "Seleccioná cuál es el pliego principal" in response.json()["error"]["message"]
