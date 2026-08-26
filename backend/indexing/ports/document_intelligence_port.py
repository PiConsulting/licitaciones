from typing import Protocol


class DocumentIntelligencePort(Protocol):
    def extract_text(self, blob_url: str) -> list[dict]:
        """Return extracted page text from a PDF source URL."""
