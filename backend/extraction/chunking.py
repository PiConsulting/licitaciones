from __future__ import annotations

import re
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("capitulos", re.compile(r"^\s*cap[ií]tulo\b", re.IGNORECASE)),
    ("articulos", re.compile(r"^\s*art[ií]culo\b", re.IGNORECASE)),
    ("anexos", re.compile(r"^\s*anexo\b", re.IGNORECASE)),
    ("incisos", re.compile(r"^\s*([a-z]\)|inciso\b)", re.IGNORECASE)),
]


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


def _infer_section_key(text: str, default_key: str = "general") -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    for section_key, pattern in _SECTION_PATTERNS:
        if pattern.search(first_line):
            return section_key
    return default_key


def _split_structural_blocks(content: str) -> list[dict[str, str]]:
    lines = content.splitlines()
    blocks: list[dict[str, str]] = []
    current_lines: list[str] = []
    current_section = "general"

    def flush() -> None:
        if not current_lines:
            return
        text = "\n".join(current_lines).strip()
        if text:
            blocks.append({"section_key": current_section, "content": text})

    for line in lines:
        if not line.strip():
            current_lines.append(line)
            continue

        detected_section = _infer_section_key(line, default_key=current_section)
        is_new_section = detected_section != current_section and bool(current_lines)
        if is_new_section:
            flush()
            current_lines = [line]
            current_section = detected_section
            continue

        if not current_lines:
            current_section = detected_section
        current_lines.append(line)

    flush()
    return blocks


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

        blocks = _split_structural_blocks(content)
        if not blocks:
            blocks = [{"section_key": "general", "content": content}]

        for block in blocks:
            tokens = _tokenize(block["content"])
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
                        "section_key": block["section_key"],
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
