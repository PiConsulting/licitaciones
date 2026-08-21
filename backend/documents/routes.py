from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from documents.schemas import DocumentSASUrlResponse
from documents.service import StoredDocument, get_document_by_id, get_document_by_id_cosmos
from shared.config import get_settings
from shared.database import SessionLocal
from users.service import get_current_user, http_bearer

router = APIRouter(prefix="/documents", tags=["documents"])


def _extract_connection_string_value(connection_string: str, key: str) -> str:
    for segment in connection_string.split(";"):
        if "=" not in segment:
            continue
        part_key, part_value = segment.split("=", 1)
        if part_key.strip().lower() == key.strip().lower():
            return part_value.strip()
    return ""


def _parse_sas_expiry(sas_token: str) -> datetime | None:
    values = parse_qs(sas_token).get("se")
    if not values:
        return None
    try:
        return datetime.fromisoformat(values[0].replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_document_for_user(document_id: str, user_id: str) -> StoredDocument | None:
    settings = get_settings()

    if settings.is_cosmos_only_mode():
        document = get_document_by_id_cosmos(document_id)
        if document is None or document.created_by != user_id:
            return None
        return document

    if SessionLocal is None:
        return None

    db = SessionLocal()
    try:
        document_sql = get_document_by_id(db, document_id)
        if document_sql is None or document_sql.created_by != user_id:
            return None
        return StoredDocument(
            id=document_sql.id,
            filename=document_sql.filename,
            blob_name=document_sql.blob_name,
            created_by=document_sql.created_by,
        )
    finally:
        db.close()


@router.get("/{document_id}/url", response_model=DocumentSASUrlResponse)
def generate_document_url(
    document_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> DocumentSASUrlResponse:
    user = get_current_user(credentials, None)

    document = _load_document_for_user(document_id, user.id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": "Documento no encontrado",
                }
            },
        )

    settings = get_settings()
    connection_string = settings.azure_blob_connection_string.strip()
    container_name = settings.azure_blob_container_name.strip()
    if not connection_string or not container_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "BLOB_CONFIGURATION_MISSING",
                    "message": "Configuración de Azure Blob incompleta",
                }
            },
        )

    blob_service = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service.get_blob_client(container=container_name, blob=document.blob_name)
    expiry = datetime.now(UTC) + timedelta(hours=1)

    account_key = _extract_connection_string_value(connection_string, "AccountKey")
    if account_key:
        sas_token = generate_blob_sas(
            account_name=blob_service.account_name,
            container_name=container_name,
            blob_name=document.blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        blob_url = f"{blob_client.url}?{sas_token}"
    else:
        # No AccountKey available (e.g. connection string built from an
        # account-level SAS) — blob_client.url already carries that SAS as
        # its query string, so it's used as-is instead of minting a new one.
        existing_sas = _extract_connection_string_value(connection_string, "SharedAccessSignature")
        if not existing_sas:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": {
                        "code": "BLOB_CONFIGURATION_MISSING",
                        "message": "No se pudo resolver credenciales para generar SAS URL",
                    }
                },
            )
        expiry = _parse_sas_expiry(existing_sas) or expiry
        blob_url = blob_client.url

    return DocumentSASUrlResponse(
        url=blob_url,
        expires_at=expiry.isoformat().replace("+00:00", "Z"),
        document_id=document.id,
        filename=document.filename,
    )
