from typing import Protocol


class SearchClientPort(Protocol):
    def upload_chunks(self, documents: list[dict]) -> None:
        """Upload chunk documents to the active vector index."""

    def delete_analysis_chunks(self, analysis_id: str) -> None:
        """Delete every indexed chunk associated with an analysis."""
