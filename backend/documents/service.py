from hashlib import sha256
from io import BytesIO

import pypdf


def calculate_content_hash(file_data: bytes) -> str:
    """Calculate SHA-256 hash from extracted PDF text, with binary fallback."""
    try:
        reader = pypdf.PdfReader(BytesIO(file_data))
        text_parts: list[str] = []

        for page in reader.pages:
            extracted = page.extract_text() or ""
            normalized = " ".join(extracted.lower().split())
            if normalized:
                text_parts.append(normalized)

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            return sha256(file_data).hexdigest()

        return sha256(full_text.encode("utf-8")).hexdigest()
    except Exception:
        return sha256(file_data).hexdigest()
