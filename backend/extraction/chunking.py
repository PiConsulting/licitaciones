from __future__ import annotations

from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    return text.split()


def _split_with_overlap(tokens: list[str], chunk_size: int, overlap: int) -> list[list[str]]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size debe ser mayor que overlap")

    chunks: list[list[str]] = []
    step = chunk_size - overlap
    for start in range(0, len(tokens), step):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        if not chunk_tokens:
            continue
        chunks.append(chunk_tokens)
        if end >= len(tokens):
            break
    return chunks


def create_chunks(
    pages: list[dict],
    document_id: str | UUID,
    correlation_id: str | UUID,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict]:
    logger.info(
        "chunking_started",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        pages=len(pages),
        chunk_size=chunk_size,
        overlap=overlap,
    )

    chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        page_number = int(page["page_number"])
        content = str(page["content"])

        paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
        if not paragraphs:
            paragraphs = [content]

        for paragraph in paragraphs:
            tokens = _tokenize(paragraph)
            if not tokens:
                continue
            for piece in _split_with_overlap(tokens, chunk_size, overlap):
                chunk_content = " ".join(piece)
                chunks.append(
                    {
                        "document_id": str(document_id),
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                        "content": chunk_content,
                        "token_count": len(piece),
                        "section_key": "general",
                    }
                )
                chunk_index += 1

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
    )
    return chunks
