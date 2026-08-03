from abc import ABC, abstractmethod


class DocumentIntelligencePort(ABC):
    @abstractmethod
    def extract_text(self, blob_reference: str) -> str:
        """Extract text from a previously uploaded document."""
