from shared.pdf_utils import calculate_content_hash_from_pdf


def calculate_content_hash(file_data: bytes) -> str:
    """Calculate SHA-256 hash from MarkItDown extracted text, with binary fallback."""
    return calculate_content_hash_from_pdf(file_data)
