from datetime import UTC, datetime, timedelta

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

from shared.ports.blob_storage import BlobStoragePort


class AzureBlobStorageAdapter(BlobStoragePort):
    def __init__(self, connection_string: str, container_name: str) -> None:
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_name = container_name
        self.container_client = self.blob_service_client.get_container_client(container_name)
        self.container_client.create_container(exist_ok=True)

    def upload(self, blob_name: str, content: bytes) -> str:
        blob_client = self.container_client.get_blob_client(blob_name)
        blob_client.upload_blob(content, overwrite=True)
        return blob_name

    def delete(self, blob_name: str) -> None:
        blob_client = self.container_client.get_blob_client(blob_name)
        blob_client.delete_blob(delete_snapshots="include")

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
