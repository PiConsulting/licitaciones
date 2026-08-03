from pathlib import Path

from shared.ports.blob_storage import BlobStoragePort


class LocalBlobStorageAdapter(BlobStoragePort):
    def __init__(self, root_directory: str) -> None:
        self.root = Path(root_directory)
        self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, blob_name: str, content: bytes) -> str:
        blob_path = self.root / blob_name
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(content)
        return blob_name

    def delete(self, blob_name: str) -> None:
        blob_path = self.root / blob_name
        if blob_path.exists():
            blob_path.unlink()

    def generate_download_url(self, blob_name: str) -> str:
        return f"local://{blob_name}"
