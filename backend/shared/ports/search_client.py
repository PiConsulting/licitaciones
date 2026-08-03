from abc import ABC, abstractmethod


class SearchClientPort(ABC):
    @abstractmethod
    def index_document(self, analysis_id: str, content: str) -> None:
        """Index extracted document content for retrieval."""
