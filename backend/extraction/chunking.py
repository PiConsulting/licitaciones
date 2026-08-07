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


def _split_heading_label_and_title(heading_text: str) -> tuple[str, str]:
    """Separa un encabezado en su etiqueta (ej. "Artículo 15º") y su título
    descriptivo (ej. "Garantía de Mantenimiento de Oferta"), cortando en el
    primer separador (guion, raya o dos puntos). Sin separador, todo el
    texto queda como etiqueta y no hay título."""
    match = re.match(r"^(.*?)\s+[-–—:]\s+(.+)$", heading_text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return heading_text.strip(), ""


def _build_heading_metadata(heading_stack: list[str]) -> dict[str, str | None]:
    """Recorre la pila de encabezados vigente (de mas general a mas
    especifico) y arma metadata estructurada: capitulo, articulo, anexo e
    inciso vigentes, mas el titulo descriptivo del encabezado mas especifico
    que tenga uno. Se usa tanto para guardar metadata rica como para
    reconstruir el encabezado a repetir cuando un articulo se divide en
    varios chunks."""
    metadata: dict[str, str | None] = {
        "chapter": None,
        "article": None,
        "anexo": None,
        "inciso": None,
        "title": None,
    }
    for heading_text in heading_stack:
        key = _infer_section_key(heading_text, default_key="general")
        label, title = _split_heading_label_and_title(heading_text)
        if key == "capitulos":
            metadata["chapter"] = label
        elif key == "articulos":
            metadata["article"] = label
        elif key == "anexos":
            metadata["anexo"] = label
        elif key == "incisos":
            metadata["inciso"] = label
        if title:
            metadata["title"] = title
    return metadata


def _heading_prefix_from_metadata(metadata: dict[str, str | None]) -> str:
    """Reconstruye el texto de encabezado (capitulo / anexo / articulo o
    inciso / titulo) a partir de la metadata, para anteponerlo al contenido
    de cada chunk final -- incluida cada sub-parte cuando un articulo largo
    se divide en varios chunks por limite de tokens, de forma que cada
    fragmento recuperado conserve el contexto."""
    lines: list[str] = []
    for key in ("chapter", "anexo"):
        value = metadata.get(key)
        if value:
            lines.append(value)
    label = metadata.get("article") or metadata.get("inciso")
    if label:
        lines.append(label)
    title = metadata.get("title")
    if title:
        lines.append(title)
    return "\n".join(lines)


def _split_structural_blocks(content: str) -> list[dict]:
    lines = content.splitlines()
    blocks: list[dict] = []
    heading_stack: list[str] = []
    body_lines: list[str] = []
    current_section = "general"
    current_path = "general"

    def flush() -> None:
        nonlocal body_lines
        text = "\n".join(body_lines).strip()
        if text:
            blocks.append(
                {
                    "section_key": current_section,
                    "section_path": current_path,
                    "section_level": len(heading_stack),
                    "content": text,
                    "is_heading": False,
                    "heading_metadata": _build_heading_metadata(heading_stack),
                }
            )
        body_lines = []

    for line in lines:
        if not line.strip():
            if body_lines:
                body_lines.append(line)
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
            continue

        if not body_lines:
            current_section = _infer_section_key(line, default_key=current_section)
            current_path = " > ".join(heading_stack) if heading_stack else current_section
        body_lines.append(line)

    flush()
    if blocks:
        return blocks

    # No hubo ningun parrafo de cuerpo, pero si se vio un encabezado (una
    # pagina que es solo un titulo, ej. portada de un anexo): igual se
    # conserva como bloque puro-encabezado en vez de perderlo.
    if heading_stack:
        return [
            {
                "section_key": current_section,
                "section_path": current_path,
                "section_level": len(heading_stack),
                "content": "",
                "is_heading": True,
                "heading_metadata": _build_heading_metadata(heading_stack),
            }
        ]

    stripped = content.strip()
    if stripped:
        return [
            {
                "section_key": "general",
                "section_path": "general",
                "section_level": 0,
                "content": stripped,
                "is_heading": False,
                "heading_metadata": _build_heading_metadata([]),
            }
        ]
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
                is_heading = block_type != "table" and (is_heading_role or looks_like_heading)

                if is_heading:
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
                        "is_heading": is_heading,
                        "heading_metadata": _build_heading_metadata(heading_stack),
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
                    "is_heading": bool(block.get("is_heading", False)),
                    "heading_metadata": block.get("heading_metadata") or _build_heading_metadata([]),
                }
            )

    return intermediate, fallback_sections


def _preceding_table_context(merged: list[dict], table_block: dict) -> str | None:
    """Determina el texto que introduce a una tabla (el parrafo justo antes,
    ej. "La evaluacion se realizara segun la siguiente tabla:") para que
    nunca quede separado de las filas que explica. Las filas siguientes de
    la misma tabla heredan el mismo contexto que la primera."""
    if not merged:
        return None

    previous = merged[-1]

    if previous.get("block_type") == "table":
        previous_ref = previous.get("table_ref") or {}
        current_ref = table_block.get("table_ref") or {}
        if previous_ref.get("table_id") is not None and previous_ref.get("table_id") == current_ref.get("table_id"):
            return previous.get("table_context")
        return None

    if previous.get("is_heading") or previous["page_number"] != table_block["page_number"]:
        return None

    same_path = previous["section_path"] == table_block["section_path"]
    is_ancestor = table_block["section_path"].startswith(f"{previous['section_path']} > ")
    if same_path or is_ancestor:
        return str(previous["content"])
    return None


def _merge_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Junta bloques relacionados en uno solo para que un encabezado (o una
    cadena capitulo > articulo > inciso) nunca quede separado del parrafo
    que lo desarrolla, y para que parrafos cortos seguidos de la misma
    seccion no generen chunks diminutos. Las tablas nunca se mezclan entre
    si (se mantienen atomicas fila por fila), pero reciben el parrafo que
    las introduce via `_preceding_table_context`. Dos casos para bloques de
    texto:
    1) mismo section_path en la misma pagina -> se concatenan.
    2) el bloque anterior es puro encabezado (aun sin parrafo propio) y el
       actual es esa misma seccion o una subseccion suya -> el encabezado
       se descarta como bloque independiente (su texto se reconstruye desde
       `heading_metadata`, que el bloque actual ya heredo al crearse).
    """
    merged: list[dict] = []

    for raw_block in blocks:
        block = dict(raw_block)

        if block.get("block_type") == "table":
            context = _preceding_table_context(merged, block)
            if context:
                block["table_context"] = context
            merged.append(block)
            continue

        if block.get("is_heading"):
            merged.append(block)
            continue

        merged_into_previous = False
        while merged:
            previous = merged[-1]
            if previous.get("block_type") == "table" or previous["page_number"] != block["page_number"]:
                break

            same_path = previous["section_path"] == block["section_path"]
            is_descendant = block["section_path"].startswith(f"{previous['section_path']} > ")

            if previous.get("is_heading") and (same_path or is_descendant):
                merged.pop()
                continue

            if not previous.get("is_heading") and same_path:
                previous["content"] = f"{previous['content']}\n\n{block['content']}"
                merged_into_previous = True
                break

            break

        if not merged_into_previous:
            merged.append(block)

    return merged


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
    blocks = _merge_intermediate_blocks(blocks)

    for block in blocks:
        try:
            page_number = int(block["page_number"])
            block_type = str(block.get("block_type", "paragraph"))
            section_key = str(block.get("section_key", "general"))
            section_path = str(block.get("section_path", section_key))
            section_level = int(block.get("section_level", 0))
            heading_metadata = block.get("heading_metadata") or {}
            heading_prefix = _heading_prefix_from_metadata(heading_metadata)
            metadata_fields = {
                "chapter": heading_metadata.get("chapter"),
                "article": heading_metadata.get("article"),
                "anexo": heading_metadata.get("anexo"),
                "inciso": heading_metadata.get("inciso"),
                "title": heading_metadata.get("title"),
            }

            if block_type == "table":
                row_content = str(block["content"])
                context_parts = [
                    part for part in (heading_prefix, block.get("table_context"), row_content) if part
                ]
                full_content = "\n\n".join(context_parts)
                row_tokens = _tokenize(full_content)
                if not row_tokens:
                    continue
                chunks.append(
                    {
                        "document_id": str(document_id),
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                        "content": full_content,
                        "token_count": len(row_tokens),
                        "section_key": section_key,
                        "section_path": section_path,
                        "section_level": section_level,
                        "block_type": "table",
                        "table_ref": block.get("table_ref"),
                        **metadata_fields,
                    }
                )
                chunk_index += 1
                continue

            # El cuerpo (sin las lineas de encabezado, que se reconstruyen
            # aparte via heading_prefix) es lo unico que se trocea por
            # limite de tokens. Si el articulo es tan largo que necesita
            # varios chunks, el encabezado se repite en cada uno para que
            # cualquier fragmento recuperado conserve el contexto.
            body = "" if block.get("is_heading") else str(block["content"]).strip()

            if body:
                heading_tokens = len(_tokenize(heading_prefix)) if heading_prefix else 0
                effective_chunk_size = max(chunk_size - heading_tokens, 1)
                effective_overlap = min(overlap, max(effective_chunk_size - 1, 0))
                content_pieces = [
                    f"{heading_prefix}\n\n{piece}" if heading_prefix else piece
                    for piece in _split_block_into_chunks(body, effective_chunk_size, effective_overlap)
                ]
            elif heading_prefix:
                content_pieces = [heading_prefix]
            else:
                content_pieces = []

            for chunk_content in content_pieces:
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
                        **metadata_fields,
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
