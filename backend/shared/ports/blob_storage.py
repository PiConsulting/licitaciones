from abc import ABC, abstractmethod


class BlobStoragePort(ABC):
    @abstractmethod
    def upload(self, blob_name: str, content: bytes) -> str:
        """Store bytes and return a reference string."""
