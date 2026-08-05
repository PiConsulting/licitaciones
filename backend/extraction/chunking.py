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

_HEADING_LINE_RE = re.compile(
    r"^\s*(cap[ií]tulo|art[ií]culo|anexo|secci[oó]n|t[ií]tulo)\b.{0,120}$",
    re.IGNORECASE,
)

_HEADING_ROLES = {"title", "sectionHeading"}


def _normalize_heading_value(text: str) -> str:
    return " ".join(text.strip().split())


def _looks_like_structured_input(pages: list[dict]) -> bool:
    return any("block_type" in item or "role" in item for item in pages)


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


def _section_path_from_stack(stack: list[str], fallback_key: str) -> tuple[str, int]:
    if stack:
        return " > ".join(stack), len(stack)
    return fallback_key, 0


def _heading_level_from_text(text: str, role: str, current_stack: list[str]) -> int:
    if role == "title":
        return 1

    first_line = text.strip().splitlines()[0] if text.strip() else ""
    numeric_match = re.match(r"^\s*(\d+(?:\.\d+)*)", first_line)
    if numeric_match:
        return min(6, len(numeric_match.group(1).split(".")) + 1)

    inferred = _infer_section_key(first_line, default_key="general")
    if inferred == "capitulos":
        return 2
    if inferred == "articulos":
        return 3
    if inferred == "anexos":
        return 2
    if inferred == "incisos":
        return 4
    return min(6, max(2, len(current_stack) + 1))


def _split_structural_blocks(content: str) -> list[dict[str, str]]:
    lines = content.splitlines()
    blocks: list[dict[str, str]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []
    current_section = "general"
    current_path = "general"

    def flush() -> None:
        nonlocal current_lines
        text = "\n".join(current_lines).strip()
        if text:
            blocks.append(
                {
                    "section_key": current_section,
                    "section_path": current_path,
                    "section_level": len(heading_stack),
                    "content": text,
                }
            )
        current_lines = []

    def is_standalone_heading(line: str) -> bool:
        stripped = line.strip()
        if not stripped or len(stripped) > 140:
            return False
        return bool(_HEADING_LINE_RE.match(stripped)) and not stripped.endswith(".")

    for line in lines:
        if not line.strip():
            current_lines.append(line)
            continue

        if is_standalone_heading(line):
            flush()
            heading_text = " ".join(line.split())
            lower = heading_text.lower()
            level = 1 if lower.startswith(("capítulo", "capitulo", "título", "titulo")) else 2
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(heading_text)
            current_section = _infer_section_key(heading_text, default_key=current_section)
            current_path = " > ".join(heading_stack)
            current_lines = [heading_text]
            continue

        if not current_lines:
            current_section = _infer_section_key(line, default_key=current_section)
            current_path = " > ".join(heading_stack) if heading_stack else current_section
        current_lines.append(line)

    flush()
    if blocks:
        return blocks

    stripped = content.strip()
    if stripped:
        return [{"section_key": "general", "section_path": "general", "section_level": 0, "content": stripped}]
    return []


def _to_intermediate_blocks(pages: list[dict]) -> tuple[list[dict], int]:
    intermediate: list[dict] = []
    fallback_sections = 0

    if _looks_like_structured_input(pages):
        ordered = sorted(
            pages,
            key=lambda item: (
                int(item.get("page_number", 0)),
                int(item.get("source_order", item.get("chunk_index", 0))),
            ),
        )
        heading_stack: list[str] = []
        fallback_section_key = "general"

        for block in ordered:
            block_type = str(block.get("block_type", "paragraph"))
            role = str(block.get("role", "paragraph") or "paragraph")
            content = str(block.get("content", "") or "").strip()
            if not content:
                continue

            if role in _HEADING_ROLES:
                heading_text = _normalize_heading_value(content)
                level = _heading_level_from_text(heading_text, role, heading_stack)
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(heading_text)
                fallback_section_key = _infer_section_key(heading_text, default_key=fallback_section_key)
            elif not heading_stack:
                new_key = _infer_section_key(content, default_key=fallback_section_key)
                if new_key != fallback_section_key:
                    fallback_sections += 1
                fallback_section_key = new_key

            section_path, section_level = _section_path_from_stack(heading_stack, fallback_section_key)
            section_key = _infer_section_key(content, default_key=fallback_section_key)

            intermediate.append(
                {
                    "page_number": int(block.get("page_number", 0)),
                    "block_type": block_type,
                    "role": role,
                    "section_key": section_key,
                    "section_path": section_path,
                    "section_level": section_level,
                    "content": content,
                    "table_ref": block.get("table_ref"),
                }
            )

        return intermediate, fallback_sections

    for page in pages:
        page_number = int(page["page_number"])
        content = str(page.get("content", "") or "")
        blocks = _split_structural_blocks(content)

        for block in blocks:
            intermediate.append(
                {
                    "page_number": page_number,
                    "block_type": "paragraph",
                    "role": "paragraph",
                    "section_key": block["section_key"],
                    "section_path": block.get("section_path", block["section_key"]),
                    "section_level": int(block.get("section_level", 0)),
                    "content": block["content"],
                    "table_ref": None,
                }
            )

    return intermediate, fallback_sections


def create_chunks(
    pages: list[dict],
    document_id: str | UUID,
    correlation_id: str | UUID,
    *,
    chunk_size: int = 700,
    overlap: int = 120,
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

    blocks, fallback_sections = _to_intermediate_blocks(pages)

    for block in blocks:
        page_number = int(block["page_number"])
        block_type = str(block.get("block_type", "paragraph"))
        section_key = str(block.get("section_key", "general"))
        section_path = str(block.get("section_path", section_key))
        section_level = int(block.get("section_level", 0))

        if block_type == "table":
            row_tokens = _tokenize(str(block["content"]))
            if not row_tokens:
                continue
            chunks.append(
                {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": str(block["content"]),
                    "token_count": len(row_tokens),
                    "section_key": section_key,
                    "section_path": section_path,
                    "section_level": section_level,
                    "block_type": "table",
                    "table_ref": block.get("table_ref"),
                }
            )
            chunk_index += 1
            continue

        tokens = _tokenize(str(block["content"]))
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
                    "section_key": section_key,
                    "section_path": section_path,
                    "section_level": section_level,
                    "block_type": "paragraph",
                    "table_ref": None,
                }
            )
            chunk_index += 1

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
        sections_by_fallback=fallback_sections,
    )
    return chunks
