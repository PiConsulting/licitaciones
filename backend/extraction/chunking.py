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

# Cantidad de terminos distintos del glossary a partir de la cual el score de
# una categoria se considera saturado (1.0). Independiente de cuantos sinonimos
# tenga cargada cada categoria.
_KEYWORD_SCORE_SATURATION = 4
# Minimo de terminos distintos para asignar una categoria como secundaria.
_SECONDARY_MIN_TERM_MATCHES = 2

# Patrones de títulos para clasificación de categorías.
#
# Se escriben en SINGULAR a propósito: el matcheo es por substring, así que el
# singular cubre también al plural ("garantia" matchea "GARANTÍAS"), pero no al
# revés. Con los patrones en plural, un pliego que titula su sección
# "GARANTÍA DE ADJUDICACIÓN" o "ANEXO I" no matcheaba nada y terminaba
# clasificado por otra palabra del título (en el caso real, "adjudicacion" ->
# criterios_evaluacion). Ese es justamente el fallo por "títulos ligeramente
# distintos" entre pliegos equivalentes.
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
        "requisito",
        "admisibilidad",
        "documentacion",
        "antecedente",
        "habilitacion",
        "condiciones de admision",
        "requisitos habilitantes",
    ],
    "garantias": [
        "garantia",
        "caucion",
        "seguro de caucion",
        "mantenimiento de oferta",
        "cumplimiento de contrato",
        "fianza",
    ],
    "plazos_clave": [
        "plazo",
        "cronograma",
        "fecha",
        "vencimiento",
        "presentacion de ofertas",
        "apertura",
    ],
    "criterios_evaluacion": [
        "evaluacion",
        "ponderacion",
        "criterio",
        "puntaje",
        "adjudicacion",
        "oferta mas conveniente",
    ],
    "causales_rechazo": [
        "rechazo",
        "descalificacion",
        "inadmisibilidad",
        "causal",
        "motivos de rechazo",
    ],
    "anexos_obligatorios": [
        "anexo",
        "formulario",
        "planilla",
        "modelo",
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


# Etiqueta de seccion numerada al inicio de una linea: "ARTICULO 10:",
# "Artículo Nº 10 -", "3.", "5.2)", "10.- GARANTÍAS. Los oferentes...".
# Es un patron estructural (numeracion + separador + titulo en mayusculas),
# no una lista de titulos conocidos: no hay nada especifico de un pliego ni
# de un organismo.
#
# MEJORA (2026-08): Regex más permisivo:
# - Separador después del título ahora es opcional ([:.])? en vez de obligatorio
# - Permite títulos que empiezan con mayúscula seguidos de texto
# - Tolera variaciones como "10.-", "10)", "Art. 10:", etc.
_RUN_IN_HEADING_RE = re.compile(
    r"^(?P<label>"
    r"(?:art[ií]culo|art\.)\s*(?:n\s*[°ºo]?\s*)?\d+[a-z]?"  # "Artículo 10", "Art. 5a"
    r"|\d{1,2}(?:\.\d{1,2})*"  # "10", "5.2", "3.1.2"
    r")"
    r"\s*[:.\-–)]?\s+"  # Separador después del label (opcional: ":", ".", "-", ")")
    r"(?P<title>[A-ZÁÉÍÓÚÑ][^\n]{2,90}?)"  # Título: empieza con mayúscula, min 3 chars
    r"(?:\s*[:.])?",  # Separador después del título (OPCIONAL)
    re.IGNORECASE,
)
_MIN_RUN_IN_TITLE_LETTERS = 3


def _looks_like_section_title(text: str) -> bool:
    """Un titulo de seccion corrido va en mayusculas (es lo que lo distingue
    visualmente del cuerpo). Exigirlo evita partir una oracion comun que apenas
    empieza con un numero, como "10. de los pagos se descontara...".
    
    MEJORA (2026-08): Toleramos títulos en mayúscula-minúscula (Title Case)
    siempre que empiecen con mayúscula y tengan al menos 50% de mayúsculas
    entre las letras. Esto captura títulos como "Garantías de la Contratación"
    que algunos pliegos escriben así en lugar de "GARANTÍAS DE LA CONTRATACIÓN".
    """
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < _MIN_RUN_IN_TITLE_LETTERS:
        return False
    
    # Debe empezar con mayúscula
    if not text[0].isupper():
        return False
    
    # Al menos 50% de las letras deben ser mayúsculas (tolera "Garantías de Oferta")
    uppercase_count = sum(1 for ch in letters if ch.isupper())
    return uppercase_count / len(letters) >= 0.5


def _promote_run_in_headings(blocks: list[dict]) -> list[dict]:
    """Convierte en encabezado propio toda etiqueta de seccion que quedo pegada
    al cuerpo del parrafo.

    Document Intelligence marca como encabezado solo lo que esta tipografica-
    mente aislado. Cuando el pliego escribe el titulo corrido con el texto
    ("Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN: En caso de corresponder, ...")
    no emite ningun `#`, y el contenido entero termina colgando de la seccion
    ANTERIOR. Eso es lo que hace que dos pliegos con la misma informacion se
    comporten distinto: en uno la seccion existe y en el otro esta sepultada
    bajo un titulo que habla de otra cosa (el caso real: la unica clausula de
    garantias de un pliego etiquetada como "ARTÍCULO 9: ADJUDICACIÓN").

    Se aplica solo a bloques de cuerpo (nunca a tablas ni a encabezados que
    Azure ya reconocio) y solo cuando la etiqueta abre un parrafo, para no
    partir el texto por una referencia cruzada tipo "lo dispuesto en el Art. 9".

    Importante: `_parse_markdown_blocks` no corta en lineas en blanco, asi que
    TODO el texto entre dos encabezados llega como un unico bloque con `\\n\\n`
    internos. Por eso hay que mirar el inicio de cada parrafo interno y no solo
    el inicio del bloque."""
    promoted: list[dict] = []

    for block in blocks:
        if block.get("heading_level") is not None or block.get("block_type") == "table":
            promoted.append(block)
            continue

        content = str(block.get("content", "")).strip()
        if not content:
            promoted.append(block)
            continue

        segments = content.split("\n\n")
        pending: list[str] = []
        emitted: list[dict] = []

        def flush_pending() -> None:
            if not pending:
                return
            body_block = dict(block)
            body_block["content"] = "\n\n".join(pending).strip()
            body_block["heading_level"] = None
            emitted.append(body_block)
            pending.clear()

        for segment in segments:
            stripped = segment.strip()
            if not stripped:
                continue

            match = _RUN_IN_HEADING_RE.match(stripped)
            title = match.group("title").strip() if match else ""
            if not match or not _looks_like_section_title(title):
                pending.append(stripped)
                continue

            body = stripped[match.end() :].strip()
            if not body:
                pending.append(stripped)
                continue

            flush_pending()

            heading_block = dict(block)
            heading_block["content"] = f"{match.group('label').strip()}: {title}"
            # Nivel 2: por debajo del titulo del documento (nivel 1) y al mismo
            # nivel que las secciones que Azure si detecta en estos pliegos.
            heading_block["heading_level"] = 2
            heading_block.pop("table_ref", None)
            emitted.append(heading_block)

            pending.append(body)

        flush_pending()
        promoted.extend(emitted or [block])

    return promoted


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


_BOILERPLATE_EDGE_CHARS = " -–—:|.,"


def _strip_boilerplate_fragments(heading: str, boilerplate: set[str]) -> str:
    """Quita del encabezado el membrete repetido que aparezca como prefijo o
    sufijo, y devuelve lo que queda (cadena vacia si era solo membrete).

    La deteccion por igualdad exacta no alcanza: basta con que en UNA pagina
    Document Intelligence fusione el membrete con el titulo real de esa pagina
    ("Municipalidad de Rosario ... PLIEGO DE CONDICIONES PARTICULARES ANEXO II")
    para que esa cadena ya no coincida con la de las otras paginas, no se
    reconozca como repetida y se cuele como ancestro de los chunks de esa
    pagina. El resultado es que la misma seccion queda etiquetada distinto segun
    la pagina, dentro de un mismo documento."""
    if not boilerplate:
        return heading

    current = heading.strip(_BOILERPLATE_EDGE_CHARS)
    # De mas largo a mas corto: si un membrete contiene a otro, conviene sacar
    # primero el mas especifico.
    ordered = sorted(boilerplate, key=len, reverse=True)

    changed = True
    while changed and current:
        changed = False
        lowered = current.lower()
        for fragment in ordered:
            if not fragment or fragment == lowered:
                continue
            if lowered.startswith(fragment):
                current = current[len(fragment) :].strip(_BOILERPLATE_EDGE_CHARS)
                changed = True
                break
            if lowered.endswith(fragment):
                current = current[: len(current) - len(fragment)].strip(_BOILERPLATE_EDGE_CHARS)
                changed = True
                break

    return current


def _to_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Recorre los bloques de Document Intelligence (encabezado si trae
    `heading_level`, parrafo o fila de tabla si no) en orden de lectura y les
    asigna `heading_path`: la lista de encabezados ancestros vigentes en ese
    punto del documento, usando directamente el nivel que ya resolvio Azure
    (cantidad de `#` en el markdown) -- sin adivinar profundidad por regex.

    Un encabezado que nunca recibe ningun parrafo/tabla propio antes de
    cerrarse (ej. la portada de un anexo que es solo un titulo) igual se
    conserva como su propio bloque puro-encabezado, para no perderlo."""
    ordered = sorted(
        blocks,
        key=lambda item: (
            int(item["page_number"]),
            int(item.get("source_order", 0)),
            int(item.get("row_order", 0)),
        ),
    )
    ordered = _promote_run_in_headings(ordered)
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
            normalized = _strip_boilerplate_fragments(normalized, boilerplate)
            if not normalized:
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

    # Scoring por categoría: cantidad de patrones que matchean y, como
    # desempate, cuál aparece ANTES en el título. En castellano el núcleo del
    # sintagma va primero, así que "GARANTÍA DE ADJUDICACIÓN" es una garantía y
    # no un criterio de adjudicación. Sin este desempate el resultado dependía
    # del orden de iteración del diccionario de patrones.
    scores: dict[str, tuple[int, int]] = {}
    for category, patterns in CATEGORY_HEADING_PATTERNS.items():
        matches = 0
        earliest = len(normalized)
        for pattern in patterns:
            position = normalized.find(_normalize_for_matching(pattern))
            if position >= 0:
                matches += 1
                earliest = min(earliest, position)
        if matches > 0:
            scores[category] = (matches, earliest)

    if not scores:
        return None

    # Mayor cantidad de matches; a igualdad, el que aparece primero.
    return min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]


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


def _count_keyword_matches(content: str, glossary: dict) -> dict[str, int]:
    """Cuenta, por categoría, cuántos términos distintos del glossary aparecen
    en el contenido del chunk."""
    normalized_content = _normalize_for_matching(content)
    content_tokens = set(normalized_content.split())

    match_counts: dict[str, int] = {}

    for category, entry in glossary.items():
        if not isinstance(entry, dict):
            continue

        query_terms = entry.get("query_terms", [])
        aliases = entry.get("aliases", [])
        all_terms = [*query_terms, *aliases]

        matches = 0
        for term in all_terms:
            normalized_term = _normalize_for_matching(str(term))
            # Split multi-word terms
            term_tokens = set(normalized_term.split())
            if term_tokens.issubset(content_tokens):
                matches += 1

        if matches > 0:
            match_counts[category] = matches

    return match_counts


def _classify_by_keywords(content: str, glossary: dict) -> dict[str, float]:
    """Score relativo de cada categoría por matching de términos clave.

    Se normaliza contra `_KEYWORD_SCORE_SATURATION` y no contra la cantidad
    total de términos de la categoría: dividir por el tamaño del glossary hacía
    que el score dependiera de cuántos sinónimos tuviera cargados cada
    categoría, no de la evidencia del chunk. Una categoría con 39 términos no
    llegaba nunca al umbral aunque el chunk la mencionara explícitamente, así
    que `secondary_categories` quedaba vacío en la práctica para todos los
    documentos."""
    match_counts = _count_keyword_matches(content, glossary)
    return {
        category: min(matches / _KEYWORD_SCORE_SATURATION, 1.0)
        for category, matches in match_counts.items()
    }


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
    
    # Fallback final: si aún no hay categoría, asignar "identificacion_procedimiento"
    # como default genérico (es la categoría menos específica)
    if not primary_category:
        primary_category = "identificacion_procedimiento"

    # Categorías secundarias: se decide por cantidad de términos distintos del
    # glossary presentes en el chunk, no por un porcentaje del glossary. Dos
    # términos distintos ya son una mención deliberada de la categoría y no una
    # coincidencia suelta.
    keyword_matches = _count_keyword_matches(content, glossary)
    secondary_categories = [
        cat
        for cat, matches in keyword_matches.items()
        if matches >= _SECONDARY_MIN_TERM_MATCHES and cat != primary_category
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
