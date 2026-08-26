from abc import ABC, abstractmethod


class BlobStoragePort(ABC):
    @abstractmethod
    def upload(self, blob_name: str, content: bytes) -> str:
        """Store bytes and return a reference string."""

    @abstractmethod
    def delete(self, blob_name: str) -> None:
        """Delete a previously uploaded blob reference."""

    @abstractmethod
    def generate_download_url(self, blob_name: str) -> str:
        """Generate a URL reference for reading a blob."""
