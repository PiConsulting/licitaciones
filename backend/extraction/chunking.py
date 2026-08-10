from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

_BOILERPLATE_MIN_PAGES = 3
_BOILERPLATE_MIN_PAGE_FRACTION = 0.5

# Patrones de títulos para clasificación de categorías
CATEGORY_HEADING_PATTERNS = {
    "objeto_alcance": [
        "objeto",
        "alcance",
        "descripcion de la contratacion",
        "alcance del servicio",
        "modalidad",
        "lugar de entrega",
    ],
    "requisitos_admisibilidad": [
        "requisitos",
        "admisibilidad",
        "documentacion",
        "antecedentes",
        "habilitacion",
        "condiciones de admision",
        "requisitos habilitantes",
    ],
    "garantias": [
        "garantias",
        "cauciones",
        "seguro de caucion",
        "mantenimiento de oferta",
        "cumplimiento de contrato",
        "fianza",
    ],
    "plazos_clave": [
        "plazos",
        "cronograma",
        "fechas",
        "vencimientos",
        "presentacion de ofertas",
        "apertura",
    ],
    "criterios_evaluacion": [
        "evaluacion",
        "ponderacion",
        "criterios",
        "puntaje",
        "adjudicacion",
        "oferta mas conveniente",
    ],
    "causales_rechazo": [
        "rechazo",
        "descalificacion",
        "inadmisibilidad",
        "causales",
        "motivos de rechazo",
    ],
    "anexos_obligatorios": [
        "anexos",
        "formularios",
        "planillas",
        "modelos",
    ],
    "identificacion_procedimiento": [
        "carátula",
        "expediente",
        "organismo",
        "procedimiento",
        "licitacion",
    ],
}


def _normalize_heading_value(text: str) -> str:
    return " ".join(text.strip().split())


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
    raw_paragraphs = content.split("\n\n")
    paragraphs = [text.strip() for text in raw_paragraphs if text.strip()]
    if paragraphs:
        return paragraphs
    return [line.strip() for line in content.splitlines() if line.strip()]


def _split_block_into_chunks(content: str, chunk_size: int, overlap: int) -> list[str]:
    """Parte el contenido de un bloque (todo el texto bajo un mismo heading_path,
    ya fusionado por `_merge_intermediate_blocks`) en chunks sin cortar ningun
    parrafo a la mitad. Acumula parrafos completos hasta el limite de tokens;
    si un parrafo individual supera el limite por si solo, se lo particiona por
    palabras de forma aislada (nunca mezclado con el contenido de otro parrafo).
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


def _detect_repeated_heading_boilerplate(
    blocks: list[dict],
    *,
    min_pages: int = _BOILERPLATE_MIN_PAGES,
    min_page_fraction: float = _BOILERPLATE_MIN_PAGE_FRACTION,
) -> set[str]:
    """Detecta encabezados que Document Intelligence marca como tales pero que
    en realidad son membrete/pie repetido en (case real: la razon social del
    organismo licitante, marcada como titulo de nivel 1 en cada pagina del
    pliego de Rosario) -- si no se filtran, terminan como ancestro de TODOS
    los chunks del documento. Solo aplica sobre encabezados (heading_level
    presente); un parrafo de cuerpo repetido no entra en este chequeo."""
    total_pages = len({int(block["page_number"]) for block in blocks}) or 1
    if total_pages < min_pages:
        return set()

    pages_by_heading: dict[str, set[int]] = defaultdict(set)
    for block in blocks:
        if block.get("heading_level") is None:
            continue
        normalized = _normalize_heading_value(str(block.get("content", ""))).lower()
        if normalized:
            pages_by_heading[normalized].add(int(block["page_number"]))

    threshold = max(min_pages, int(total_pages * min_page_fraction))
    return {text for text, pages in pages_by_heading.items() if len(pages) >= threshold}


def _to_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Recorre los bloques de Document Intelligence (encabezado si trae
    `heading_level`, parrafo o fila de tabla si no) en orden de lectura y les
    asigna `heading_path`: la lista de encabezados ancestros vigentes en ese
    punto del documento, usando directamente el nivel que ya resolvio Azure
    (cantidad de `#` en el markdown) -- sin adivinar profundidad por regex.

    Un encabezado que nunca recibe ningun parrafo/tabla propio antes de
    cerrarse (ej. la portada de un anexo que es solo un titulo) igual se
    conserva como su propio bloque puro-encabezado, para no perderlo."""
    ordered = sorted(blocks, key=lambda item: (int(item["page_number"]), int(item.get("source_order", 0))))
    boilerplate = _detect_repeated_heading_boilerplate(ordered)

    heading_stack: list[tuple[str, int]] = []
    heading_has_body: list[bool] = []
    intermediate: list[dict] = []
    last_page = 1

    def current_path() -> list[str]:
        return [text for text, _level in heading_stack]

    def pop_to_level(level: int, page_number: int) -> None:
        while heading_stack and heading_stack[-1][1] >= level:
            text, _popped_level = heading_stack.pop()
            had_body = heading_has_body.pop()
            if not had_body:
                intermediate.append(
                    {
                        "page_number": page_number,
                        "block_type": "paragraph",
                        "content": "",
                        "table_ref": None,
                        "heading_path": current_path() + [text],
                        "is_heading": True,
                    }
                )

    for block in ordered:
        content = str(block.get("content", "")).strip()
        if not content:
            continue
        last_page = int(block["page_number"])
        level = block.get("heading_level")

        if level is not None:
            normalized = _normalize_heading_value(content)
            if normalized.lower() in boilerplate:
                continue
            pop_to_level(int(level), last_page)
            heading_stack.append((normalized, int(level)))
            heading_has_body.append(False)
            continue

        if heading_has_body:
            heading_has_body[-1] = True

        intermediate.append(
            {
                "page_number": last_page,
                "block_type": block.get("block_type", "paragraph"),
                "content": content,
                "table_ref": block.get("table_ref"),
                "heading_path": current_path(),
                "is_heading": False,
            }
        )

    pop_to_level(0, last_page)
    return intermediate


def _preceding_table_context(merged: list[dict], table_block: dict) -> str | None:
    """Determina el texto que introduce a una tabla (el parrafo justo antes,
    ej. "La evaluacion se realizara segun la siguiente tabla:") para que nunca
    quede separado de las filas que explica. Las filas siguientes de la misma
    tabla heredan el mismo contexto que la primera."""
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

    prev_path = previous.get("heading_path") or []
    table_path = table_block.get("heading_path") or []
    same_path = prev_path == table_path
    is_ancestor = len(prev_path) < len(table_path) and table_path[: len(prev_path)] == prev_path
    if same_path or is_ancestor:
        return str(previous["content"])
    return None


def _merge_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Junta parrafos consecutivos que comparten el mismo heading_path en un
    solo bloque, para que un encabezado nunca quede separado del texto que lo
    desarrolla y para que parrafos cortos seguidos de la misma seccion no
    generen chunks diminutos. Las tablas nunca se mezclan entre si (se
    mantienen atomicas fila por fila), pero reciben el parrafo que las
    introduce via `_preceding_table_context`."""
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

        if merged:
            previous = merged[-1]
            can_merge = (
                previous.get("block_type") != "table"
                and not previous.get("is_heading")
                and previous["page_number"] == block["page_number"]
                and previous.get("heading_path") == block.get("heading_path")
            )
            if can_merge:
                previous["content"] = f"{previous['content']}\n\n{block['content']}"
                continue

        merged.append(block)

    return merged


def _normalize_for_matching(text: str) -> str:
    """Normaliza texto para matching (lowercase, sin acentos, sin puntuación)"""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    # Remover puntuación, mantener espacios
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def _classify_by_heading(heading_path: list[str]) -> str | None:
    """Clasifica chunk por título de sección"""
    if not heading_path:
        return None

    heading_text = " ".join(heading_path).lower()
    normalized = _normalize_for_matching(heading_text)

    # Scoring por categoría
    scores: dict[str, int] = {}
    for category, patterns in CATEGORY_HEADING_PATTERNS.items():
        score = sum(1 for pattern in patterns if _normalize_for_matching(pattern) in normalized)
        if score > 0:
            scores[category] = score

    if not scores:
        return None

    # Retornar categoría con mayor score
    return max(scores.items(), key=lambda x: x[1])[0]


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict]:
    """Carga el glossary.json para clasificación por keywords"""
    from pathlib import Path
    import json

    glossary_path = Path(__file__).resolve().parents[1] / "analysis" / "extraction" / "glossary.json"
    if not glossary_path.exists():
        return {}

    with glossary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _classify_by_keywords(content: str, glossary: dict) -> dict[str, float]:
    """Calcula score de cada categoría por matching de términos clave"""
    normalized_content = _normalize_for_matching(content)
    content_tokens = set(normalized_content.split())

    category_scores: dict[str, float] = {}

    for category, entry in glossary.items():
        if not isinstance(entry, dict):
            continue

        query_terms = entry.get("query_terms", [])
        aliases = entry.get("aliases", [])
        all_terms = [*query_terms, *aliases]

        # Contar términos que aparecen en el contenido
        matches = 0
        for term in all_terms:
            normalized_term = _normalize_for_matching(str(term))
            # Split multi-word terms
            term_tokens = set(normalized_term.split())
            if term_tokens.issubset(content_tokens):
                matches += 1

        if matches > 0:
            # Score normalizado por cantidad de términos de la categoría
            category_scores[category] = matches / len(all_terms) if all_terms else 0.0

    return category_scores


def classify_chunk_categories(chunk: dict) -> dict:
    """Clasifica un chunk en categorías.

    Returns:
        {
            "primary_category": str | None,
            "secondary_categories": list[str],
            "category_scores": dict[str, float]
        }
    """
    glossary = _load_glossary()
    heading_path = chunk.get("heading_path", [])
    content = chunk.get("content", "")

    # 1. Clasificación por título
    heading_category = _classify_by_heading(heading_path)

    # 2. Clasificación por keywords
    keyword_scores = _classify_by_keywords(content, glossary)

    # 3. Determinar categoría primary y secundarias
    primary_category = heading_category  # El título tiene prioridad

    # Si no hay título claro, usar keyword matching
    if not primary_category and keyword_scores:
        # La categoría con mayor score es la primary
        primary_category = max(keyword_scores.items(), key=lambda x: x[1])[0]

    # Categorías secundarias: cualquier score > threshold
    SECONDARY_THRESHOLD = 0.15  # Al menos 15% de términos match
    secondary_categories = [
        cat
        for cat, score in keyword_scores.items()
        if score >= SECONDARY_THRESHOLD and cat != primary_category
    ]

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": keyword_scores,
    }


def create_chunks(
    blocks: list[dict],
    document_id: str | UUID,
    correlation_id: str | UUID,
    *,
    chunk_size: int = 700,
    overlap: int = 120,
) -> list[dict]:
    """Arma los chunks finales a partir de los bloques que devuelve
    `extraction.document_intelligence.extract_text()` (encabezado/parrafo/fila
    de tabla con pagina y, si es encabezado, su nivel ya resuelto por Azure).
    Cada chunk final es siempre "heading_path completo + su contenido" -- nunca
    un titulo suelto ni un parrafo sin contexto de que seccion es."""
    logger.info(
        "chunking_started",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        blocks=len(blocks),
        chunk_size=chunk_size,
        overlap=overlap,
    )

    intermediate = _to_intermediate_blocks(blocks)
    intermediate = _merge_intermediate_blocks(intermediate)

    chunks: list[dict] = []
    chunk_index = 0

    for block in intermediate:
        try:
            page_number = int(block["page_number"])
            block_type = str(block.get("block_type", "paragraph"))
            heading_path = list(block.get("heading_path") or [])
            heading_prefix = "\n".join(heading_path)
            section_path = " > ".join(heading_path) if heading_path else "general"

            if block_type == "table":
                row_content = str(block["content"])
                context_parts = [part for part in (heading_prefix, block.get("table_context"), row_content) if part]
                full_content = "\n\n".join(context_parts)
                row_tokens = _tokenize(full_content)
                if not row_tokens:
                    continue

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": full_content,
                    "token_count": len(row_tokens),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "block_type": "table",
                    "table_ref": block.get("table_ref"),
                }

                # Clasificar categorías del chunk
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
                continue

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

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": chunk_content,
                    "token_count": len(_tokenize(chunk_content)),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "block_type": "paragraph",
                    "table_ref": None,
                }

                # Clasificar categorías del chunk
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chunking_block_skipped",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                heading_path=block.get("heading_path"),
                page_number=block.get("page_number"),
                error=str(exc),
            )
            continue

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
    )
    return chunks
