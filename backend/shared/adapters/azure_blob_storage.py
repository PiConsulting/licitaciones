from datetime import UTC, datetime, timedelta
import logging

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
from azure.core.exceptions import HttpResponseError, ResourceExistsError

from shared.ports.blob_storage import BlobStoragePort

logger = logging.getLogger(__name__)


class AzureBlobStorageAdapter(BlobStoragePort):
    def __init__(self, connection_string: str, container_name: str) -> None:
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_name = container_name
        self.container_client = self.blob_service_client.get_container_client(container_name)
        try:
            self.container_client.create_container()
        except ResourceExistsError:
            pass
        except HttpResponseError as exc:
            # With SAS scoped to an existing container, create permissions may be absent.
            # Continue and let upload/read operations enforce their own permissions.
            if exc.error_code in {"AuthorizationFailure", "AuthorizationPermissionMismatch"}:
                logger.warning(
                    "blob_container_create_skipped_due_to_permissions",
                    extra={"container_name": container_name, "error_code": exc.error_code},
                )
            else:
                raise

    def upload(self, blob_name: str, content: bytes) -> str:
        blob_client = self.container_client.get_blob_client(blob_name)
        blob_client.upload_blob(content, overwrite=True)
        return blob_name

    def delete(self, blob_name: str) -> None:
        blob_client = self.container_client.get_blob_client(blob_name)
        try:
            blob_client.delete_blob(delete_snapshots="include")
        except ResourceNotFoundError:
            logger.warning("blob_delete_skipped_missing_blob", extra={"blob_name": blob_name})

    def generate_download_url(self, blob_name: str) -> str:
        blob_client = self.container_client.get_blob_client(blob_name)

        account_name = self.blob_service_client.account_name
        credential = self.blob_service_client.credential
        account_key = getattr(credential, "account_key", None)
        if account_key is None:
            return blob_client.url

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(hours=1),
        )
        return f"{blob_client.url}?{sas_token}"
