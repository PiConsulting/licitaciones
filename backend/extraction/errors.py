class ExtractionError(Exception):
    """Base error for extraction/indexing pipeline."""


class DocumentTextExtractionError(ExtractionError):
    """Raised when the text for one document cannot be extracted."""


class TransientExtractionError(ExtractionError):
    """Raised for temporary upstream errors that can be retried."""
