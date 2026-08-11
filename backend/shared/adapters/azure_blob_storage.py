from datetime import UTC, datetime, timedelta
import logging
import os

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
    
    def download_to_temp(self, blob_name: str, temp_path: str) -> None:
        """Descarga un blob a un archivo temporal.
        
        FIX CRÍTICO (2026-08): Necesario para calcular highlights con PyMuPDF
        en Azure. El archivo debe ser limpiado manualmente por el caller.
        
        FIX MEDIUM (#7): Ahora valida que el directorio sea writable antes de
        intentar la descarga.
        
        Args:
            blob_name: Nombre del blob en Azure
            temp_path: Ruta absoluta donde guardar el archivo temporal
        
        Raises:
            ResourceNotFoundError: Si el blob no existe
            OSError: Si el directorio no existe o no es writable
            IOError: Si falla la escritura del archivo
        """
        from pathlib import Path
        
        # Validar que el directorio padre exista
        temp_file_path = Path(temp_path)
        temp_dir = temp_file_path.parent
        
        if not temp_dir.exists():
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
                logger.info(
                    "temp_directory_created",
                    path=str(temp_dir),
                    blob_name=blob_name,
                )
            except OSError as exc:
                logger.error(
                    "temp_directory_creation_failed",
                    path=str(temp_dir),
                    blob_name=blob_name,
                    error=str(exc),
                )
                raise OSError(f"Cannot create temp directory {temp_dir}: {exc}") from exc
        
        # Validar que el directorio sea writable
        if not os.access(temp_dir, os.W_OK):
            logger.error(
                "temp_directory_not_writable",
                path=str(temp_dir),
                blob_name=blob_name,
            )
            raise OSError(f"Temp directory {temp_dir} is not writable")
        
        # Descargar el blob
        blob_client = self.container_client.get_blob_client(blob_name)
        try:
            with open(temp_path, "wb") as temp_file:
                download_stream = blob_client.download_blob()
                temp_file.write(download_stream.readall())
            logger.debug(
                "blob_downloaded_to_temp",
                blob_name=blob_name,
                temp_path=temp_path,
            )
        except IOError as exc:
            logger.error(
                "blob_download_io_error",
                blob_name=blob_name,
                temp_path=temp_path,
                error=str(exc),
            )
            raise IOError(f"Failed to write blob {blob_name} to {temp_path}: {exc}") from exc

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
