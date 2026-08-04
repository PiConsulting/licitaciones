from typing import Protocol


class SearchClientPort(Protocol):
    def upload_chunks(self, documents: list[dict]) -> None:
        """Upload chunk documents to the active vector index."""
