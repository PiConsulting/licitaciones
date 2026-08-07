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

# Encabezados por palabra clave: cubre la convencion mas comun (capitulo/articulo/
# anexo/seccion/titulo), incluyendo la abreviatura "Art.". No es el unico criterio:
# ver `_looks_like_heading_line` para el resto de convenciones (numeradas, mayuscula
# sostenida, Title Case) que hacen que la deteccion no dependa de un vocabulario fijo.
_HEADING_LINE_RE = re.compile(
    r"^\s*(cap[ií]tulo|art[ií]culo|art\.\s|anexo|secci[oó]n|t[ií]tulo)",
    re.IGNORECASE,
)

# Encabezados numerados a cualquier profundidad ("1.11 Garantias", "3.2.13.4. Retiro
# de las muestras", "10.1.2. De fiel cumplimiento..."). Exige que la palabra siguiente
# al numero empiece en mayuscula para no confundir con una oracion de cuerpo que
# arranca con un numero ("10 dias habiles siguientes...").
_NUMBERED_HEADING_RE = re.compile(r"^\s*\d{1,3}(?:\.\d{1,3}){0,5}\.?\s+[A-ZÁÉÍÓÚÑ]")

_LOWERCASE_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en",
    "que", "y", "o", "u", "pero", "con", "sin", "por", "para", "su", "sus",
    "al", "se", "es", "son", "no", "mas", "más", "esta", "este", "estos", "estas",
}

_HEADING_ROLES = {"title", "sectionHeading"}


def _is_all_caps_heading(stripped: str) -> bool:
    letters = [ch for ch in stripped if ch.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return (upper / len(letters)) >= 0.9


def _is_title_case_heading(stripped: str) -> bool:
    words = [word for word in stripped.split() if word]
    if not (2 <= len(words) <= 10):
        return False
    first_word = words[0].lower().strip(":,.()")
    if first_word in _LOWERCASE_STOPWORDS:
        return False
    capitalized = sum(1 for word in words if word[:1].isupper())
    return (capitalized / len(words)) >= 0.8


def _looks_like_heading_line(line: str) -> bool:
    """Heuristica agnostica de formato para detectar un titulo de seccion, sin
    depender de una lista fija de palabras clave. Reconoce (en orden de señal
    mas fuerte a mas debil): palabras clave conocidas, numeracion jerarquica
    ("1.11", "3.2.13.4."), mayuscula sostenida ("GARANTIAS") y Title Case
    ("Garantias De Mantenimiento"). Pensada para funcionar sobre pliegos de
    cualquier jurisdiccion, no solo los que usan una convencion conocida.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 140 or stripped.endswith("."):
        return False
    if _HEADING_LINE_RE.match(stripped):
        return True
    if len(stripped) <= 100 and _NUMBERED_HEADING_RE.match(stripped):
        return True
    if len(stripped) <= 80 and (_is_all_caps_heading(stripped) or _is_title_case_heading(stripped)):
        return True
    return False


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


def _split_into_paragraphs(content: str) -> list[str]:
    raw_paragraphs = re.split(r"\n\s*\n", content)
    paragraphs = [text.strip() for text in raw_paragraphs if text.strip()]
    if paragraphs:
        return paragraphs
    return [line.strip() for line in content.splitlines() if line.strip()]


def _split_block_into_chunks(content: str, chunk_size: int, overlap: int) -> list[str]:
    """Parte el contenido de un bloque (encabezado + texto hasta el proximo
    encabezado) en chunks sin cortar ningun parrafo a la mitad. Acumula
    parrafos completos hasta el limite de tokens; si un parrafo individual
    supera el limite por si solo, se lo particiona por palabras de forma
    aislada (nunca mezclado con el contenido de otro parrafo).
    """
    paragraphs = _split_into_paragraphs(content)
    if not paragraphs:
        return []

    paragraph_tokens = [_tokenize(paragraph) for paragraph in paragraphs]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for paragraph, tokens in zip(paragraphs, paragraph_tokens):
        if len(tokens) > chunk_size:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            for piece in _split_with_overlap(tokens, chunk_size, overlap):
                chunks.append(" ".join(piece))
            continue

        if current and current_tokens + len(tokens) > chunk_size:
            chunks.append("\n\n".join(current))
            carried: list[str] = []
            carried_tokens = 0
            for prev_paragraph in reversed(current):
                prev_tokens = len(_tokenize(prev_paragraph))
                if carried and carried_tokens + prev_tokens > overlap:
                    break
                carried.insert(0, prev_paragraph)
                carried_tokens += prev_tokens
                if carried_tokens >= overlap:
                    break
            current = carried
            current_tokens = carried_tokens

        current.append(paragraph)
        current_tokens += len(tokens)

    if current:
        chunks.append("\n\n".join(current))

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

    for line in lines:
        if not line.strip():
            current_lines.append(line)
            continue

        if _looks_like_heading_line(line):
            flush()
            heading_text = " ".join(line.split())
            lower = heading_text.lower()
            role_hint = "title" if lower.startswith(("capítulo", "capitulo", "título", "titulo")) else "sectionHeading"
            level = _heading_level_from_text(heading_text, role_hint, heading_stack)
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
            try:
                block_type = str(block.get("block_type", "paragraph"))
                role = str(block.get("role", "paragraph") or "paragraph")
                content = str(block.get("content", "") or "").strip()
                if not content:
                    continue

                is_heading_role = role in _HEADING_ROLES
                # El rol que informa el proveedor de OCR no siempre es preciso.
                # Si el bloque es una sola linea y "parece" un encabezado (misma
                # heuristica agnostica que el modo texto plano), lo tratamos como
                # tal aunque el rol diga "paragraph".
                looks_like_heading = (
                    not is_heading_role
                    and block_type == "paragraph"
                    and "\n" not in content
                    and _looks_like_heading_line(content)
                )

                if is_heading_role or looks_like_heading:
                    heading_text = _normalize_heading_value(content)
                    effective_role = role if is_heading_role else "sectionHeading"
                    level = _heading_level_from_text(heading_text, effective_role, heading_stack)
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
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "chunking_structured_block_skipped",
                    page_number=block.get("page_number"),
                    error=str(exc),
                )
                continue

        return intermediate, fallback_sections

    for page in pages:
        try:
            page_number = int(page["page_number"])
            content = str(page.get("content", "") or "")
            blocks = _split_structural_blocks(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chunking_page_skipped", page_number=page.get("page_number"), error=str(exc))
            continue

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
        try:
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

            for chunk_content in _split_block_into_chunks(str(block["content"]), chunk_size, overlap):
                if not chunk_content.strip():
                    continue
                chunks.append(
                    {
                        "document_id": str(document_id),
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                        "content": chunk_content,
                        "token_count": len(_tokenize(chunk_content)),
                        "section_key": section_key,
                        "section_path": section_path,
                        "section_level": section_level,
                        "block_type": "paragraph",
                        "table_ref": None,
                    }
                )
                chunk_index += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chunking_block_skipped",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                section_path=block.get("section_path"),
                page_number=block.get("page_number"),
                error=str(exc),
            )
            continue

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
        sections_by_fallback=fallback_sections,
    )
    return chunks
