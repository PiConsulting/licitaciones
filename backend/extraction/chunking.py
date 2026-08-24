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


_PARENT_CHILD_MIN_CHARS = 800

_INCISO_MIN_SUBSTANTIVE_CHARS = 100

_INCISO_PATTERN = re.compile(
    r"^(?P<label>[a-z]\)|[ivxIVX]+\)|[0-9]+[.)])\s+(?P<text>.+)",
    re.MULTILINE,
)


def _detect_incisos(content: str) -> list[dict]:
    """Detecta incisos (a), b), 1., 2., i), ii)...) dentro de un artículo largo.

    PARENT/CHILD CHUNKING (US-3.1): esto es lo que decide si un chunk se deja
    plano o se subdivide en un chunk "parent" (contexto completo) + N chunks
    "child" (uno por inciso, más precisos para retrieval). Devuelve lista
    vacía -- y por lo tanto ninguna subdivisión -- si hay menos de 2 incisos
    o si alguno queda por debajo de `_INCISO_MIN_SUBSTANTIVE_CHARS`.

    Returns:
        [{"label": "a)", "start": int, "end": int, "text": str}, ...]
    """
    matches = list(_INCISO_PATTERN.finditer(content))
    if len(matches) < 2:
        return []

    incisos = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index < len(matches) - 1 else len(content)
        text = content[start:end].strip()
        if len(text) < _INCISO_MIN_SUBSTANTIVE_CHARS:
            return []
        incisos.append({"label": match.group("label"), "start": start, "end": end, "text": text})

    return incisos


_KEYWORD_SCORE_SATURATION = 4

_DENSITY_SATURATION_PER_100_WORDS = 1.0

_DEFAULT_PRIMARY_THRESHOLD = 0.25
_DEFAULT_SECONDARY_THRESHOLD = 0.12

# FASE 2 (plan RAG v2, 2026-08-24): thresholds de clasificación semántica por
# similitud coseno (ver `_classify_by_semantic_similarity` más abajo). Están
# en otra escala que los de arriba (densidad de keywords, 0-1 saturado) --
# similitud coseno entre embeddings de texto real suele vivir en un rango más
# angosto y alto. Son un punto de partida razonable, NO calibrados contra
# datos reales todavía -- calibrar con el dataset de evaluación (plan,
# sección 6) antes de confiar en ellos para decisiones de producción.
_DEFAULT_SEMANTIC_PRIMARY_THRESHOLD = 0.60
_DEFAULT_SEMANTIC_SECONDARY_THRESHOLD = 0.48

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
    # FASE 2 (plan RAG v2, 2026-08-24): faltaba por completo -- "riesgos" es
    # una categoría de extracción real (ver analysis/extraction/prompts/
    # riesgos.txt) pero nunca podía ganar por heading match, porque no había
    # ninguna entrada acá. Un chunk bajo un encabezado literal "Riesgos" caía
    # directo a clasificación por keywords (más débil) o quedaba sin
    # categoría. Términos genéricos de encabezado, no vocabulario de un
    # pliego puntual -- mismo criterio que las demás categorías de esta
    # tabla.
    "riesgos": [
        "riesgo",
        "riesgos para el oferente",
        "consideraciones comerciales",
        "aspectos a considerar",
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

            max_carry = min(overlap, chunk_size - len(tokens))
            carried: list[str] = []
            carried_tokens = 0
            if max_carry > 0:
                for prev_paragraph in reversed(current):
                    prev_tokens = len(_tokenize(prev_paragraph))
                    if carried_tokens + prev_tokens > max_carry:
                        break
                    carried.insert(0, prev_paragraph)
                    carried_tokens += prev_tokens

            current = carried
            current_tokens = carried_tokens

        current.append(paragraph)
        current_tokens += len(tokens)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


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
    """
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < _MIN_RUN_IN_TITLE_LETTERS:
        return False
    if not text[0].isupper():
        return False
    uppercase_count = sum(1 for ch in letters if ch.isupper())
    return uppercase_count / len(letters) >= 0.5


def _promote_run_in_headings(blocks: list[dict]) -> list[dict]:
    """Convierte en encabezado propio toda etiqueta de seccion que quedo pegada
    al cuerpo del parrafo."""
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
    sufijo, y devuelve lo que queda (cadena vacia si era solo membrete)."""
    if not boilerplate:
        return heading

    current = heading.strip(_BOILERPLATE_EDGE_CHARS)
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


_SPLIT_WORD_MAX_CHARS = 5


_PALABRAS_CORTAS_COMPLETAS = {
    "EL",
    "LA",
    "LO",
    "LOS",
    "LAS",
    "UN",
    "UNA",
    "UNOS",
    "UNAS",
    "DE",
    "DEL",
    "AL",
    "A",
    "EN",
    "Y",
    "O",
    "U",
    "POR",
    "CON",
    "SIN",
    "SU",
    "SUS",
    "ES",
    "SE",
    "NO",
    "SI",
    "QUE",
    "PARA",
    "SOBRE",
}


def _join_split_heading(current: str, following: str) -> str:
    """Une las dos mitades de un encabezado partido entre páginas.."""
    izquierda = str(current or "").rstrip()
    derecha = str(following or "").lstrip()
    if not izquierda:
        return derecha
    if not derecha:
        return izquierda

    ultimo = izquierda.split()[-1]
    primero = derecha.split()[0]

    completa_izquierda = ultimo.upper() in _PALABRAS_CORTAS_COMPLETAS
    completa_derecha = primero.upper() in _PALABRAS_CORTAS_COMPLETAS

    pedazo_izquierdo = (
        not completa_izquierda and _is_upper_run(ultimo) and len(ultimo) <= _SPLIT_WORD_MAX_CHARS
    )
    pedazo_derecho = not completa_derecha and (
        (_is_upper_run(primero) and len(primero) <= _SPLIT_WORD_MAX_CHARS) or primero[0].islower()
    )

    palabra_partida = (
        izquierda[-1].isalpha()
        and derecha[0].isalpha()
        and not completa_izquierda
        and (pedazo_izquierdo or pedazo_derecho)
    )

    return f"{izquierda}{derecha}" if palabra_partida else f"{izquierda} {derecha}"


def _merge_split_headings_across_pages(blocks: list[dict]) -> list[dict]:
    """Detecta y fusiona encabezados que Document Intelligence partió entre páginas."""
    import re

    if not blocks:
        return blocks

    merged: list[dict] = []
    skip_next = False

    for i, block in enumerate(blocks):
        if skip_next:
            skip_next = False
            continue

        level = block.get("heading_level")
        if level is None or i == len(blocks) - 1:
            merged.append(block)
            continue
        content = str(block.get("content", "")).strip()
        next_block = blocks[i + 1]
        next_level = next_block.get("heading_level")
        next_content = str(next_block.get("content", "")).strip()

        if next_level == level and int(next_block["page_number"]) == int(block["page_number"]) + 1:
            words_current = content.split()
            words_next = next_content.split()

            if not words_current or not words_next:
                merged.append(block)
                continue

            last_word_current = words_current[-1]
            first_word_next = words_next[0]

            is_roman_current = bool(re.match(r"^[IVXLCDM]+$", last_word_current, re.IGNORECASE))
            is_roman_next = bool(re.match(r"^[IVXLCDM]+$", first_word_next, re.IGNORECASE))

            next_starts_lowercase = first_word_next[0].islower()

            next_starts_with_short_fragment = (
                len(first_word_next) < 4
                and first_word_next.isupper()
                and not is_roman_next
                and not first_word_next[-1] in ".,:;"  # No es abreviación
            )

            current_ends_with_colon = last_word_current.endswith(":")
            next_starts_with_article = first_word_next.upper() in [
                "EL",
                "LA",
                "LOS",
                "LAS",
                "DE",
                "DEL",
            ]

            likely_continuation = (
                current_ends_with_colon
                and not next_starts_with_article
                and len(first_word_next) < 6  # Fragmento corto después de ":"
            )

            is_fragmented = (
                next_starts_lowercase or next_starts_with_short_fragment or likely_continuation
            )

            if is_fragmented:
                merged_content = _join_split_heading(content, next_content)
                merged_block = {**block}  # Mantener metadata del primero
                merged_block["content"] = merged_content

                logger.info(
                    "merged_split_heading",
                    page_from=block["page_number"],
                    page_to=next_block["page_number"],
                    original_parts=[content, next_content],
                    merged=merged_content,
                )

                merged.append(merged_block)
                skip_next = True
                continue

        merged.append(block)

    return merged


_HEADING_TAIL_MAX_CHARS = 90


def _first_bbox_on_page(block: dict) -> dict | None:
    """Primer bounding box del bloque que corresponde a su propia página."""
    page_number = block.get("page_number")
    for bbox in block.get("bbox") or []:
        if not isinstance(bbox, dict):
            continue
        if bbox.get("page") == page_number and "y" in bbox:
            return bbox
    return None


def _starts_on_same_line(heading: dict, body: dict) -> bool:
    """¿El cuerpo arranca en la MISMA línea visual que el encabezado?

    Es la firma estructural de que Document Intelligence partió una sola línea
    del PDF en dos "párrafos": el bbox del cuerpo empieza a la misma altura que
    el del encabezado, porque su primer renglón ES la continuación del título.

    Se usa esto y no una heurística sobre las palabras (largo del fragmento,
    listas de términos conocidos) porque es una propiedad del documento, no del
    vocabulario de un pliego en particular.
    """
    heading_bbox = _first_bbox_on_page(heading)
    body_bbox = _first_bbox_on_page(body)
    if heading_bbox is None or body_bbox is None:
        return False

    heading_height = float(heading_bbox.get("height") or 0)
    if heading_height <= 0:
        return False

    return abs(float(body_bbox["y"]) - float(heading_bbox["y"])) <= heading_height * 0.7


def _is_upper_run(text: str) -> bool:
    """Tirada en mayúsculas: se ignoran dígitos, símbolos y puntuación."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return all(ch.isupper() for ch in letters)


def _split_heading_tail(content: str) -> tuple[str, str] | None:
    """Separa el contenido en (cola del título, cuerpo real), o None.

    Dos formas, las dos observadas en pliegos reales:
      a) "ANTÍA DE ADJUDICACIÓN: En caso de corresponder, ..." -> la cola
         termina en ':' y después sigue el cuerpo;
      b) "ZO DE ENTREGA" -> el bloque entero es la cola, sin cuerpo.
    """
    stripped = str(content or "").strip()
    if not stripped:
        return None
    if (
        "\n" not in stripped
        and len(stripped) <= _HEADING_TAIL_MAX_CHARS
        and _is_upper_run(stripped)
    ):
        return stripped, ""
    tail, separator, rest = stripped.partition(":")
    if not separator or not rest.strip():
        return None
    if len(tail) > _HEADING_TAIL_MAX_CHARS or not _is_upper_run(tail):
        return None
    return tail.strip(), rest.strip()


def _join_heading_tail(heading_text: str, tail: str) -> str:
    """Une el encabezado con su cola, con o sin espacio según corresponda.

    Sin espacio cuando la palabra quedó cortada al medio ("GAR" + "ANTÍA",
    "PLA" + "ZO"); con espacio cuando el corte cayó justo en un límite de
    palabra ("PLAZO" + "DE ENTREGA").
    """
    heading_text = heading_text.rstrip()
    if not heading_text or not tail:
        return f"{heading_text}{tail}".strip()

    last_token = heading_text.split()[-1]

    looks_truncated = (
        heading_text[-1].isalpha()
        and tail[0].isalpha()
        and _is_upper_run(last_token)
        and len(last_token) <= 5
    )
    return f"{heading_text}{tail}" if looks_truncated else f"{heading_text} {tail}"


def _merge_truncated_headings_with_body(blocks: list[dict]) -> list[dict]:
    """Reconstruye los encabezados que Document Intelligence cortó al medio."""
    merged: list[dict] = []
    skip_indexes: set[int] = set()

    for index, block in enumerate(blocks):
        if index in skip_indexes:
            continue

        if block.get("heading_level") is None or index + 1 >= len(blocks):
            merged.append(block)
            continue

        body = blocks[index + 1]
        if (
            body.get("heading_level") is not None
            or body.get("block_type") == "table"
            or int(body.get("page_number", -1)) != int(block.get("page_number", -2))
            or not _starts_on_same_line(block, body)
        ):
            merged.append(block)
            continue

        split = _split_heading_tail(str(body.get("content", "")))
        if split is None:
            merged.append(block)
            continue

        tail, remaining_body = split
        heading_block = dict(block)
        heading_block["content"] = _join_heading_tail(str(block.get("content", "")), tail)
        merged.append(heading_block)

        logger.info(
            "merged_truncated_heading_with_body",
            page=block.get("page_number"),
            heading_before=str(block.get("content", ""))[:60],
            heading_after=heading_block["content"][:80],
            body_remainder_chars=len(remaining_body),
        )

        if remaining_body:
            body_block = dict(body)
            body_block["content"] = remaining_body
            merged.append(body_block)

        skip_indexes.add(index + 1)

    return merged


def _normalize_numbered_heading_levels(blocks: list[dict]) -> list[dict]:
    """Normaliza los niveles de headings con patron numerico consecutivo
    (1. OBJETO, 2. REQUISITOS, 3. GARANTÍAS...) para que sean hermanos
    en lugar de hijos, independientemente de lo que Azure DI detectó.

    Azure DI a veces detecta niveles diferentes (## vs ###) para headings
    que son semanticamente del mismo nivel (secciones numeradas consecutivas).
    """
    import re

    logger.info(
        "normalize_function_called",
        total_blocks=len(blocks),
    )

    numbered_pattern = re.compile(r"^(\d+)\.\s+[A-ZÁÉÍÓÚÑ].*", re.IGNORECASE)

    headings_found = [
        (i, block.get("heading_level"), block.get("content", "")[:60])
        for i, block in enumerate(blocks)
        if block.get("heading_level") is not None
    ]
    if headings_found:
        logger.info("normalize_scan_start", total_headings=len(headings_found))
        for idx, level, content in headings_found[:10]:
            logger.info("heading_content", index=idx, level=level, content=content)

    sequences: list[list[int]] = []
    current_sequence: list[int] = []
    expected_number = 1

    for i, block in enumerate(blocks):
        level = block.get("heading_level")
        if level is None:
            continue

        content = str(block.get("content", "")).strip()
        match = numbered_pattern.match(content)

        if match:
            number = int(match.group(1))
            if number == expected_number:
                current_sequence.append(i)
                expected_number += 1
                logger.info("sequence_item_added", index=i, number=number, content=content[:60])
            else:
                if len(current_sequence) >= 2:
                    sequences.append(current_sequence)
                    logger.info("sequence_completed_non_consecutive", length=len(current_sequence))
                current_sequence = [i] if number == 1 else []
                expected_number = 2 if number == 1 else 1
        else:
            if len(current_sequence) >= 2:
                sequences.append(current_sequence)
                logger.info("sequence_completed_non_numbered", length=len(current_sequence))
            current_sequence = []
            expected_number = 1

    if len(current_sequence) >= 2:
        sequences.append(current_sequence)

    normalized = blocks.copy()
    for sequence_indices in sequences:
        min_level = min(normalized[i]["heading_level"] for i in sequence_indices)

        for i in sequence_indices:
            normalized[i] = {**normalized[i], "heading_level": min_level}

        logger.info(
            "normalized_heading_sequence",
            indices=sequence_indices,
            target_level=min_level,
            headings=[normalized[i]["content"][:50] for i in sequence_indices[:5]],
        )

    return normalized


_DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+\S")


def _decimal_heading_depth(content: object) -> int | None:
    """Profundidad que el propio encabezado declara: `1.` → 1, `3.1.2.` → 3."""
    texto = str(content or "").strip().replace("\\", "")
    match = _DECIMAL_HEADING_RE.match(texto)
    return len(match.group(1).split(".")) if match else None


def _normalize_decimal_heading_levels(blocks: list[dict]) -> list[dict]:
    """El nivel de un encabezado decimal lo dice su numeración, no Azure DI."""
    profundidades: list[tuple[int, int]] = []
    for indice, block in enumerate(blocks):
        if block.get("heading_level") is None:
            continue
        profundidad = _decimal_heading_depth(block.get("content"))
        if profundidad is not None:
            profundidades.append((indice, profundidad))

    if not any(profundidad >= 2 for _, profundidad in profundidades):
        return blocks

    niveles_raiz = [int(blocks[i]["heading_level"]) for i, p in profundidades if p == 1]
    if niveles_raiz:
        base = min(niveles_raiz)
    else:
        profundidad_min = min(p for _, p in profundidades)
        base = min(
            int(blocks[i]["heading_level"]) for i, p in profundidades if p == profundidad_min
        )
        base -= profundidad_min - 1

    normalizados = list(blocks)
    cambios: list[tuple[str, int, int]] = []
    for indice, profundidad in profundidades:
        if profundidad < 2:
            continue
        objetivo = base + profundidad - 1
        actual = int(blocks[indice]["heading_level"])
        if objetivo != actual:
            normalizados[indice] = {**normalizados[indice], "heading_level": objetivo}
            cambios.append((str(blocks[indice].get("content", ""))[:50], actual, objetivo))

    if cambios:
        logger.info(
            "niveles_de_encabezado_decimal_normalizados",
            cambios=len(cambios),
            nivel_base=base,
            muestra=cambios[:5],
        )
    return normalizados


_TOP_LEVEL_DIVISION_RE = re.compile(r"^(?:anexo|ap[eé]ndice)\b", re.IGNORECASE)


def _nest_unnumbered_headings_under_numbered(blocks: list[dict]) -> list[dict]:
    """Un encabezado sin numerar que aparece después de uno numerado cuelga de él."""
    indices_encabezados = [i for i, b in enumerate(blocks) if b.get("heading_level") is not None]
    if not any(_decimal_heading_depth(blocks[i].get("content")) for i in indices_encabezados):
        return blocks

    normalizados = list(blocks)
    cambios: list[tuple[str, int, int]] = []
    piso: int | None = None
    tramo: list[int] = []

    def cerrar_tramo() -> None:
        if piso is None or not tramo:
            return
        minimo = min(int(blocks[i]["heading_level"]) for i in tramo)
        delta = piso - minimo
        if delta <= 0:
            return
        for indice in tramo:
            actual = int(blocks[indice]["heading_level"])
            normalizados[indice] = {**normalizados[indice], "heading_level": actual + delta}
            cambios.append((str(blocks[indice].get("content", ""))[:50], actual, actual + delta))

    for indice in indices_encabezados:
        contenido = str(blocks[indice].get("content", "")).strip()
        if _decimal_heading_depth(contenido) is not None or _TOP_LEVEL_DIVISION_RE.match(contenido):
            cerrar_tramo()
            tramo = []
            if _decimal_heading_depth(contenido) is not None:
                piso = int(blocks[indice]["heading_level"]) + 1
            continue
        if piso is not None:
            tramo.append(indice)

    cerrar_tramo()

    if cambios:
        logger.info(
            "encabezados_sin_numerar_anidados_bajo_su_seccion",
            cambios=len(cambios),
            muestra=cambios[:5],
        )
    return normalizados


_INDEX_MIN_ENTRIES = 5
_INDEX_MIN_NUMBERED_RATIO = 0.75
_INDEX_MIN_DISTINCT_TARGETS = 3
_INDEX_MIN_SECTION_PREFIX_RATIO = 0.6

_COL_PREFIX_RE = re.compile(r"^col_\d+:\s*", re.MULTILINE)
_TRAILING_NUMBER_RE = re.compile(r"(?:^|\s)(\d{1,3})\s*$")
_ONLY_NUMBER_RE = re.compile(r"^\d{1,3}$")

_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\.\s")


def _index_entries(blocks: list[dict]) -> list[str]:
    """Las entradas de una posible tabla de contenidos, una por renglón lógico.

    Las filas de tabla vienen como `col_1: <título>\\ncol_2: <página>`, y en la
    variante en párrafos el número de página puede venir como su propio bloque.
    Se normalizan las dos formas al mismo texto plano y se pega cada número
    suelto a la entrada anterior, que es a la que pertenece.
    """
    entradas: list[str] = []
    for block in blocks:
        texto = _COL_PREFIX_RE.sub("", str(block.get("content", "") or ""))
        texto = " ".join(texto.replace("\\", "").split())
        if not texto:
            continue
        if _ONLY_NUMBER_RE.match(texto) and entradas:
            entradas[-1] = f"{entradas[-1]} {texto}"
            continue
        entradas.append(texto)
    return entradas


def _looks_like_index_listing(entradas: list[str], pagina: int, paginas_totales: int) -> bool:
    """¿Este grupo de bloques es el índice del pliego?"""
    if len(entradas) < _INDEX_MIN_ENTRIES:
        return False

    numeros: list[int] = []
    con_prefijo = 0
    for entrada in entradas:
        match = _TRAILING_NUMBER_RE.search(entrada)
        if match:
            numeros.append(int(match.group(1)))
        if _SECTION_NUMBER_RE.match(entrada):
            con_prefijo += 1

    if len(numeros) / len(entradas) < _INDEX_MIN_NUMBERED_RATIO:
        return False
    if len(set(numeros)) < _INDEX_MIN_DISTINCT_TARGETS:
        return False
    if numeros != sorted(numeros):
        return False
    if max(numeros) <= pagina or max(numeros) > paginas_totales:
        return False
    return con_prefijo / len(entradas) >= _INDEX_MIN_SECTION_PREFIX_RATIO


def _drop_index_listings(blocks: list[dict]) -> list[dict]:
    """Saca del pipeline los bloques que son el índice del pliego (CHK-13)."""
    if not blocks:
        return blocks

    paginas_totales = max((_safe_page(b) for b in blocks), default=1)
    descartar: set[int] = set()

    por_tabla: dict[object, list[int]] = {}
    for indice, block in enumerate(blocks):
        table_id = _table_group_key(block)
        if table_id is not None:
            por_tabla.setdefault(table_id, []).append(indice)

    for indices in por_tabla.values():
        grupo = [blocks[i] for i in indices]
        pagina = min(_safe_page(b) for b in grupo)
        if _looks_like_index_listing(_index_entries(grupo), pagina, paginas_totales):
            descartar.update(indices)

    inicio = 0
    while inicio < len(blocks):
        block = blocks[inicio]
        if block.get("table_ref") or block.get("heading_level") is not None:
            inicio += 1
            continue
        pagina = _safe_page(block)
        fin = inicio
        while (
            fin < len(blocks)
            and not blocks[fin].get("table_ref")
            and blocks[fin].get("heading_level") is None
            and _safe_page(blocks[fin]) == pagina
        ):
            fin += 1
        grupo = blocks[inicio:fin]
        if _looks_like_index_listing(_index_entries(grupo), pagina, paginas_totales):
            descartar.update(range(inicio, fin))
        inicio = fin

    if not descartar:
        return blocks

    logger.info(
        "indice_del_pliego_descartado",
        bloques_descartados=len(descartar),
        bloques_totales=len(blocks),
        paginas=sorted({_safe_page(blocks[i]) for i in descartar}),
        muestra=[str(blocks[i].get("content", ""))[:60] for i in sorted(descartar)[:3]],
    )
    return [block for indice, block in enumerate(blocks) if indice not in descartar]


_PAGE_FURNITURE_MAX_CHARS = 120
_PAGE_FURNITURE_MIN_PAGES = 3
_PAGE_FURNITURE_MIN_PAGE_FRACTION = 0.6


def _drop_repeated_page_furniture(blocks: list[dict]) -> list[dict]:
    """Saca los párrafos cortos que se repiten en casi todas las páginas."""
    paginas = {_safe_page(block) for block in blocks}
    if len(paginas) < _PAGE_FURNITURE_MIN_PAGES:
        return blocks

    umbral = max(_PAGE_FURNITURE_MIN_PAGES, int(len(paginas) * _PAGE_FURNITURE_MIN_PAGE_FRACTION))

    paginas_por_texto: dict[str, set[int]] = defaultdict(set)
    for block in blocks:
        if block.get("heading_level") is not None or block.get("table_ref"):
            continue
        texto = " ".join(str(block.get("content", "") or "").split())
        if texto and len(texto) <= _PAGE_FURNITURE_MAX_CHARS:
            paginas_por_texto[texto.lower()].add(_safe_page(block))

    membrete = {
        texto
        for texto, paginas_vistas in paginas_por_texto.items()
        if len(paginas_vistas) >= umbral
    }
    if not membrete:
        return blocks

    conservados = []
    descartados = 0
    for block in blocks:
        if block.get("heading_level") is None and not block.get("table_ref"):
            texto = " ".join(str(block.get("content", "") or "").split()).lower()
            if texto in membrete:
                descartados += 1
                continue
        conservados.append(block)
    logger.info(
        "membrete_de_pagina_descartado",
        bloques_descartados=descartados,
        textos=sorted(membrete)[:5],
        paginas_del_documento=len(paginas),
        umbral_de_paginas=umbral,
    )
    return conservados


def _safe_page(block: dict) -> int:
    try:
        return int(block.get("page_number") or 1)
    except (TypeError, ValueError):
        return 1


def _table_group_key(block: dict) -> object | None:
    """Clave para agrupar las filas de una misma tabla, sea cual sea la forma
    de `table_ref`.
    """
    table_ref = block.get("table_ref")
    if isinstance(table_ref, dict):
        return table_ref.get("table_id")
    if isinstance(table_ref, str) and table_ref:
        return table_ref
    return None


def _to_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Recorre los bloques de Document Intelligence (encabezado si trae
    `heading_level`, parrafo o fila de tabla si no) en orden de lectura y les
    asigna `heading_path`: la lista de encabezados ancestros vigentes en ese
    punto del documento, usando directamente el nivel que ya resolvio Azure
    (cantidad de `#` en el markdown) -- sin adivinar profundidad por regex."""
    ordered = sorted(
        blocks,
        key=lambda item: (
            int(item["page_number"]),
            int(item.get("source_order", 0)),
            int(item.get("row_order", 0)),
        ),
    )

    ordered = _drop_index_listings(ordered)

    ordered = _drop_repeated_page_furniture(ordered)

    ordered = _merge_split_headings_across_pages(ordered)

    ordered = _merge_truncated_headings_with_body(ordered)

    ordered = _normalize_numbered_heading_levels(ordered)

    ordered = _normalize_decimal_heading_levels(ordered)
    ordered = _promote_run_in_headings(ordered)

    ordered = _nest_unnumbered_headings_under_numbered(ordered)
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

            logger.debug(
                "heading_detected",
                page=last_page,
                level=level,
                text=normalized[:80],
                current_stack=[h for h, _ in heading_stack],
            )

            pop_to_level(int(level), last_page)
            heading_stack.append((normalized, int(level)))
            heading_has_body.append(False)
            continue

        if heading_has_body:
            for index in range(len(heading_has_body)):
                heading_has_body[index] = True

        intermediate.append(
            {
                "page_number": last_page,
                "block_type": block.get("block_type", "paragraph"),
                "content": content,
                "table_ref": block.get("table_ref"),
                "heading_path": current_path(),
                "is_heading": False,
                "para_id": block.get("para_id"),  # DEFINITIVO V2: Propagar para_id
                "bbox": block.get("bbox", []),
                **({"lines": block["lines"]} if block.get("lines") else {}),
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
        if previous_ref.get("table_id") is not None and previous_ref.get(
            "table_id"
        ) == current_ref.get("table_id"):
            return previous.get("table_context")
        return None

    if previous.get("is_heading") or previous["page_number"] != table_block["page_number"]:
        return None

    prev_path = previous.get("heading_path") or []
    table_path = table_block.get("heading_path") or []
    same_path = prev_path == table_path
    is_ancestor = len(prev_path) < len(table_path) and table_path[: len(prev_path)] == prev_path
    if same_path or is_ancestor:
        return _introductory_tail(previous["content"])
    return None


_TABLE_CONTEXT_MAX_CHARS = 300


def _introductory_tail(content: object) -> str | None:
    """La frase que introduce a la tabla: el ÚLTIMO párrafo del bloque previo."""
    texto = str(content or "").strip()
    if not texto:
        return None

    parrafos = [parte.strip() for parte in texto.split("\n\n") if parte.strip()]
    if not parrafos:
        return None

    cola = parrafos[-1]
    if len(cola) <= _TABLE_CONTEXT_MAX_CHARS:
        return cola

    recorte = cola[-_TABLE_CONTEXT_MAX_CHARS:]
    for separador in (". ", "; ", ": "):
        posicion = recorte.find(separador)
        if 0 <= posicion < len(recorte) // 2:
            return recorte[posicion + len(separador) :].strip()
    espacio = recorte.find(" ")
    return recorte[espacio + 1 :].strip() if espacio >= 0 else recorte.strip()


def _merge_intermediate_blocks(blocks: list[dict]) -> list[dict]:
    """Junta bloques consecutivos que comparten el mismo heading_path en un
    solo bloque semántico para RAG.
    """
    from shared.config import get_settings

    settings = get_settings()
    max_table_tokens = settings.chunking_max_table_tokens

    merged: list[dict] = []

    for raw_block in blocks:
        block = dict(raw_block)

        if block.get("block_type") == "table":
            context = _preceding_table_context(merged, block)
            if context:
                block["table_context"] = context
            if merged:
                previous = merged[-1]
                previous_ref = previous.get("table_ref") or {}
                current_ref = block.get("table_ref") or {}
                same_table = (
                    previous.get("block_type") == "table"
                    and previous_ref.get("table_id") is not None
                    and previous_ref.get("table_id") == current_ref.get("table_id")
                )

                if same_table:
                    if "merged_blocks" not in previous:
                        original_content = previous["content"]
                        previous["merged_blocks"] = [
                            {
                                "para_id": previous.get("para_id"),
                                "bbox": previous.get("bbox", []),
                                **({"lines": previous["lines"]} if previous.get("lines") else {}),
                                "content": original_content,
                            }
                        ]
                    combined_content = f"{previous['content']}\n{block['content']}"
                    approx_tokens = len(combined_content) / 4

                    if approx_tokens > max_table_tokens:
                        block["table_context"] = previous.get("table_context", "")
                        block["merged_blocks"] = [
                            {
                                "para_id": block.get("para_id"),
                                "bbox": block.get("bbox", []),
                                **({"lines": block["lines"]} if block.get("lines") else {}),
                                "content": block.get("content", ""),
                            }
                        ]
                        merged.append(block)
                        continue
                    previous["merged_blocks"].append(
                        {
                            "para_id": block.get("para_id"),
                            "bbox": block.get("bbox", []),
                            **({"lines": block["lines"]} if block.get("lines") else {}),
                            "content": block.get("content", ""),
                        }
                    )

                    previous["content"] = combined_content

                    if "table_ref" in previous and "row_index" in current_ref:
                        previous["table_ref"]["row_index"] = current_ref["row_index"]

                    continue  # No agregar block actual, ya está mergeado

            if "merged_blocks" not in block:
                block["merged_blocks"] = [
                    {
                        "para_id": block.get("para_id"),
                        "bbox": block.get("bbox", []),
                        **({"lines": block["lines"]} if block.get("lines") else {}),
                        "content": block.get("content", ""),
                    }
                ]
            merged.append(block)
            continue

        if block.get("is_heading"):
            if "merged_blocks" not in block:
                block["merged_blocks"] = []
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
                if "merged_blocks" not in previous:
                    original_content = previous["content"]
                    previous["merged_blocks"] = [
                        {
                            "para_id": previous.get("para_id"),
                            "bbox": previous.get("bbox", []),
                            **({"lines": previous["lines"]} if previous.get("lines") else {}),
                            "content": original_content,
                        }
                    ]
                previous["merged_blocks"].append(
                    {
                        "para_id": block.get("para_id"),
                        "bbox": block.get("bbox", []),
                        **({"lines": block["lines"]} if block.get("lines") else {}),
                        "content": block.get("content", ""),
                    }
                )
                previous["content"] = f"{previous['content']}\n\n{block['content']}"
                continue
        if "merged_blocks" not in block:
            block["merged_blocks"] = [
                {
                    "para_id": block.get("para_id"),
                    "bbox": block.get("bbox", []),
                    **({"lines": block["lines"]} if block.get("lines") else {}),
                    "content": block.get("content", ""),
                }
            ]
        merged.append(block)

    return merged


def _normalize_for_matching(text: str) -> str:
    """Normaliza texto para matching (lowercase, sin acentos, sin puntuación)"""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def _classify_single_heading(heading: str) -> str | None:
    """Clasifica UN encabezado (no una ruta) contra los patrones de categoría.

    Scoring por categoría: cantidad de patrones que matchean y, como desempate,
    cuál aparece ANTES en el título. En castellano el núcleo del sintagma va
    primero, así que "GARANTÍA DE ADJUDICACIÓN" es una garantía y no un
    criterio de adjudicación. Sin este desempate el resultado dependía del
    orden de iteración del diccionario de patrones.
    """
    normalized = _normalize_for_matching(heading.lower())
    if not normalized:
        return None

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
    return min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]


def _classify_by_heading(heading_path: list[str]) -> str | None:
    """Clasifica un chunk por su título de sección, de la hoja hacia la raíz."""
    if not heading_path:
        return None

    for heading in reversed(heading_path):
        category = _classify_single_heading(str(heading))
        if category is not None:
            return category

    return None


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict]:
    """Carga el glossary.json para clasificación por keywords"""
    from pathlib import Path
    import json

    glossary_path = (
        Path(__file__).resolve().parents[1] / "analysis" / "extraction" / "glossary.json"
    )
    if not glossary_path.exists():
        return {}

    with glossary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _semantic_classification_enabled() -> bool:
    """Flag de activación de la Fase 2 (plan RAG v2, 4.3). Default False --
    sin esto activado, `classify_chunk_categories` se comporta exactamente
    igual que antes de esta fase. Import perezoso para no acoplar
    `chunking.py` (hoy sin dependencias externas) a `shared.config` salvo
    cuando efectivamente hace falta consultarlo."""
    try:
        from shared.config import get_settings

        return bool(get_settings().chunking_use_semantic_classification)
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_classification_flag_unavailable", error=str(exc)[:200])
        return False


@lru_cache(maxsize=1)
def _load_category_definitions() -> dict[str, dict]:
    """Carga category_definitions.json para clasificación semántica (Fase 2,
    4.3). Config versionada, no en código -- ver el archivo para el
    razonamiento completo."""
    from pathlib import Path
    import json

    definitions_path = (
        Path(__file__).resolve().parents[1]
        / "analysis"
        / "extraction"
        / "category_definitions.json"
    )
    if not definitions_path.exists():
        return {}

    with definitions_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _category_definition_embeddings() -> dict[str, tuple[float, ...]]:
    """Embeddings de la definición semántica de cada categoría, cacheados una
    sola vez por proceso -- son ~9 textos cortos que no cambian salvo que se
    edite `category_definitions.json` (y el proceso se reinicia si eso pasa,
    como con cualquier `lru_cache` a nivel módulo).

    Si el servicio de embeddings no está disponible (sin credenciales, red
    caída, etc.) se degrada a `{}` en vez de propagar la excepción -- la
    clasificación semántica es un fallback opcional sobre heading+keywords,
    nunca debe tumbar el chunking completo de un análisis.
    """
    definitions = _load_category_definitions()
    if not definitions:
        return {}
    try:
        from extraction.embeddings import embed_query
    except Exception as exc:  # noqa: BLE001
        logger.warning("category_definitions_embedding_unavailable", error=str(exc)[:200])
        return {}

    embeddings: dict[str, tuple[float, ...]] = {}
    for category, entry in definitions.items():
        if not isinstance(entry, dict):
            continue
        definition_text = entry.get("definition")
        if not definition_text:
            continue
        try:
            embeddings[category] = tuple(embed_query(definition_text))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "category_definition_embedding_failed",
                category=category,
                error=str(exc)[:200],
            )
    return embeddings


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _classify_by_semantic_similarity(content: str) -> dict[str, float]:
    """Fase 2 (plan RAG v2, 4.3): similitud coseno entre un embedding del
    contenido del chunk y el embedding de la definición semántica de cada
    categoría.

    Se usa SOLO como fallback -- ver el llamador en `classify_chunk_
    categories` -- cuando ni el heading ni las keywords del glosario
    encontraron una categoría primaria con confianza suficiente. Es la señal
    más cara de las tres (una llamada real a Azure OpenAI Embeddings, aunque
    cacheada por texto normalizado vía `embed_query`), así que se reserva
    para el caso que realmente la necesita: contenido con vocabulario que el
    glosario no contempla, que es exactamente el problema que esta fase
    ataca (ver plan, sección 4.3).
    """
    category_embeddings = _category_definition_embeddings()
    if not category_embeddings or not content.strip():
        return {}

    try:
        from extraction.embeddings import embed_query

        content_embedding = embed_query(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chunk_semantic_classification_failed", error=str(exc)[:200])
        return {}

    return {
        category: _cosine_similarity(content_embedding, list(definition_embedding))
        for category, definition_embedding in category_embeddings.items()
    }


def _term_appears_in(normalized_term: str, content_tokens: set[str], padded_content: str) -> bool:
    """¿El término del glosario aparece en el chunk?"""
    if not normalized_term:
        return False
    tokens = normalized_term.split()
    if len(tokens) == 1:
        return tokens[0] in content_tokens
    return f" {normalized_term} " in padded_content


def _count_keyword_matches(content: str, glossary: dict) -> dict[str, int]:
    """Cuenta, por categoría, cuántos términos distintos del glossary aparecen
    en el contenido del chunk."""
    normalized_content = _normalize_for_matching(content)
    content_tokens = set(normalized_content.split())
    padded_content = f" {normalized_content} "

    match_counts: dict[str, int] = {}

    for category, entry in glossary.items():
        if not isinstance(entry, dict):
            continue

        query_terms = entry.get("query_terms", [])
        aliases = entry.get("aliases", [])
        all_terms = [*query_terms, *aliases]

        matches = 0
        for term in all_terms:
            if _term_appears_in(_normalize_for_matching(str(term)), content_tokens, padded_content):
                matches += 1

        if matches > 0:
            match_counts[category] = matches

    return match_counts


def _compute_density_score(
    match_count: int, content_length: int, category_weight: float = 1.0
) -> float:
    """Calcula score normalizado por densidad de keywords en el contenido."""
    if match_count == 0 or content_length == 0:
        return 0.0
    term_coverage = min(match_count / _KEYWORD_SCORE_SATURATION, 1.0)
    words_per_100 = max(content_length / 100.0, 1.0)
    matches_per_100_words = match_count / words_per_100
    keyword_density = min(matches_per_100_words / _DENSITY_SATURATION_PER_100_WORDS, 1.0)
    score = term_coverage * keyword_density * category_weight

    return min(score, 1.0)  # Cap at 1.0


def _classify_by_keywords(content: str, glossary: dict) -> dict[str, float]:
    """Score relativo de cada categoría por matching de términos clave.

    CAMBIO v2 (2026-08-12): Score basado en DENSIDAD adaptativa en vez de
    conteo simple. Usa thresholds configurables por categoría.

    Fórmula: density_score = term_coverage * keyword_density * category_weight

    Ver _compute_density_score() para detalles."""
    match_counts = _count_keyword_matches(content, glossary)
    content_length = len(content.split())

    scores = {}
    for category, match_count in match_counts.items():
        entry = glossary.get(category, {})
        category_weight = entry.get("weight", 1.0) if isinstance(entry, dict) else 1.0

        score = _compute_density_score(match_count, content_length, category_weight)
        scores[category] = score

    return scores


def classify_chunk_categories(chunk: dict) -> dict:
    """Clasifica un chunk en categorías usando scoring adaptativo por densidad."""
    glossary = _load_glossary()
    heading_path = chunk.get("heading_path", [])
    content = chunk.get("content", "")
    chunk_id = chunk.get("chunk_id", "unknown")

    heading_category = _classify_by_heading(heading_path)

    keyword_scores = _classify_by_keywords(content, glossary)

    primary_category = heading_category  # El título tiene prioridad

    if not primary_category and keyword_scores:
        candidates = []
        for cat, score in keyword_scores.items():
            entry = glossary.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            primary_threshold = thresholds.get("primary", _DEFAULT_PRIMARY_THRESHOLD)

            if score >= primary_threshold:
                candidates.append((cat, score))

        if candidates:
            primary_category = max(candidates, key=lambda x: x[1])[0]

            if len(candidates) > 1:
                sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
                top_score = sorted_candidates[0][1]
                close_competitors = [c for c in sorted_candidates[1:] if c[1] >= top_score * 0.85]

                if close_competitors:
                    logger.info(
                        "chunk_classification_ambiguous",
                        chunk_id=chunk_id,
                        primary_chosen=primary_category,
                        primary_score=round(top_score, 3),
                        close_competitors={c[0]: round(c[1], 3) for c in close_competitors},
                        heading_path=" > ".join(heading_path) if heading_path else None,
                    )

    # FASE 2 (plan RAG v2, 2026-08-24, sección 4.3): si ni el heading ni las
    # keywords del glosario encontraron una categoría primaria, el chunk
    # probablemente usa vocabulario que el glosario no contempla -- que es
    # justo la debilidad que motivó esta fase. Se intenta un fallback
    # semántico (similitud coseno contra la definición de cada categoría)
    # ANTES de resolver secondary_categories, para que el resultado semántico
    # también pueda participar como primary. Detrás de un flag (default
    # False): sin activarlo, este bloque nunca corre y el comportamiento es
    # idéntico al de antes de esta fase.
    semantic_scores: dict[str, float] = {}
    if not primary_category and _semantic_classification_enabled():
        semantic_scores = _classify_by_semantic_similarity(content)
        if semantic_scores:
            definitions = _load_category_definitions()
            semantic_candidates = []
            for cat, score in semantic_scores.items():
                entry = definitions.get(cat, {})
                thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
                primary_threshold = thresholds.get(
                    "primary", _DEFAULT_SEMANTIC_PRIMARY_THRESHOLD
                )
                if score >= primary_threshold:
                    semantic_candidates.append((cat, score))

            if semantic_candidates:
                primary_category = max(semantic_candidates, key=lambda x: x[1])[0]
                logger.info(
                    "chunk_classification_semantic_fallback_used",
                    chunk_id=chunk_id,
                    primary_chosen=primary_category,
                    score=round(max(score for _cat, score in semantic_candidates), 3),
                    heading_path=" > ".join(heading_path) if heading_path else None,
                    reason="sin match de heading ni de keywords del glosario",
                )

    secondary_categories = []
    for cat, score in keyword_scores.items():
        if cat == primary_category:
            continue  # No incluir la primary en secondary

        entry = glossary.get(cat, {})
        thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
        secondary_threshold = thresholds.get("secondary", _DEFAULT_SECONDARY_THRESHOLD)

        if score >= secondary_threshold:
            secondary_categories.append(cat)

    if semantic_scores:
        definitions = _load_category_definitions()
        for cat, score in semantic_scores.items():
            if cat == primary_category or cat in secondary_categories:
                continue  # No duplicar la primary ni lo que keywords ya agregó

            entry = definitions.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            secondary_threshold = thresholds.get(
                "secondary", _DEFAULT_SEMANTIC_SECONDARY_THRESHOLD
            )
            if score >= secondary_threshold:
                secondary_categories.append(cat)

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": keyword_scores,
        "semantic_scores": semantic_scores or None,
    }


def _blocks_data_for(block: dict, texto: str, page_number: int) -> list[dict]:
    """Los bloques originales que efectivamente están en `texto`."""
    merged_blocks = block.get("merged_blocks") or []
    if not merged_blocks:
        return [
            {
                "para_id": block.get("para_id"),
                "page": page_number,
                "bbox": block.get("bbox", []),
                **({"lines": block["lines"]} if block.get("lines") else {}),
                "content": block.get("content", ""),
            }
        ]

    texto_normalizado = _normalize_for_matching(texto)
    incluidos = [
        mb
        for mb in merged_blocks
        if (contenido := _normalize_for_matching(str(mb.get("content", ""))))
        and contenido in texto_normalizado
    ]

    if not incluidos:
        incluidos = merged_blocks

    return [
        {
            "para_id": mb.get("para_id"),
            "page": page_number,
            "bbox": mb.get("bbox", []),
            **({"lines": mb["lines"]} if mb.get("lines") else {}),
            "content": mb.get("content", ""),
        }
        for mb in incluidos
    ]


_PROGRAMMING_ERRORS = (NameError, AttributeError, TypeError)


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
    saltados: list[dict] = []

    for block in intermediate:
        try:
            page_number = int(block["page_number"])
            block_type = str(block.get("block_type", "paragraph"))
            heading_path = list(block.get("heading_path") or [])

            section_path = " > ".join(heading_path) if heading_path else "general"
            title = heading_path[-1] if heading_path else None  # Último nivel = título de sección

            if block_type == "table":
                row_content = str(block["content"])
                context_parts = [block.get("table_context"), row_content]
                full_content = "\n\n".join([p for p in context_parts if p])
                row_tokens = _tokenize(full_content)
                if not row_tokens:
                    continue

                blocks_data = _blocks_data_for(block, full_content, page_number)

                source = {
                    "page": page_number,
                    "block_type": "table",
                    "blocks": blocks_data,
                }

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": full_content,  # SOLO table_context + rows (sin heading)
                    "token_count": len(row_tokens),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "title": title,  # RAG: Campo explícito para embedding
                    "block_type": "table",
                    "table_ref": block.get("table_ref"),
                    "source": source,  # RAG PHASE 3: Metadata estructurada para highlighting
                    "blocks": blocks_data,  # LEGACY: Mantener por compatibilidad
                    "chunk_type": "normal",
                }
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
                continue

            if block.get("is_heading"):
                heading_text = heading_path[-1] if heading_path else ""
                content_pieces = [heading_text] if heading_text else []
            else:
                body = str(block["content"]).strip()
                content_pieces = _split_block_into_chunks(body, chunk_size, overlap) if body else []

            for chunk_content in content_pieces:
                if not chunk_content.strip():
                    continue

                blocks_data = _blocks_data_for(block, chunk_content, page_number)

                source = {
                    "page": page_number,
                    "block_type": "paragraph",
                    "blocks": blocks_data,
                }

                chunk_dict = {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": chunk_content,  # SOLO el párrafo puro (sin heading)
                    "token_count": len(_tokenize(chunk_content)),
                    "heading_path": heading_path,
                    "heading_level": len(heading_path),
                    "section_path": section_path,
                    "title": title,  # RAG: Campo explícito para embedding
                    "block_type": "paragraph",
                    "table_ref": None,
                    "source": source,  # RAG PHASE 3: Metadata estructurada para highlighting
                    "blocks": blocks_data,  # LEGACY: Mantener por compatibilidad
                    "chunk_type": "normal",
                }

                incisos = (
                    _detect_incisos(chunk_content)
                    if len(chunk_content) >= _PARENT_CHILD_MIN_CHARS
                    else []
                )

                if incisos:
                    parent_index = chunk_index
                    chunk_dict["chunk_type"] = "parent"

                    classification = classify_chunk_categories(chunk_dict)
                    chunk_dict["primary_category"] = classification["primary_category"]
                    chunk_dict["secondary_categories"] = classification["secondary_categories"]

                    child_indices: list[int] = []
                    child_chunk_dicts: list[dict] = []
                    for inciso in incisos:
                        chunk_index += 1
                        inciso_label = inciso["label"].rstrip(").")
                        child_content = inciso["text"]

                        child_source = {
                            "page": page_number,
                            "block_type": "paragraph",
                            "blocks": _blocks_data_for(block, child_content, page_number),
                        }
                        child_dict = {
                            **chunk_dict,
                            "chunk_index": chunk_index,
                            "content": child_content,
                            "token_count": len(_tokenize(child_content)),
                            "title": f"{title}.{inciso_label}" if title else inciso_label,
                            "section_path": f"{section_path} > {inciso['label']}",
                            "chunk_type": "child",
                            "parent_chunk_index": parent_index,
                            "source": child_source,
                            "blocks": list(child_source["blocks"]),
                        }
                        child_dict.pop("child_chunk_indices", None)

                        child_classification = classify_chunk_categories(child_dict)
                        child_dict["primary_category"] = child_classification["primary_category"]
                        child_dict["secondary_categories"] = child_classification[
                            "secondary_categories"
                        ]
                        child_chunk_dicts.append(child_dict)
                        child_indices.append(chunk_index)

                    chunk_dict["child_chunk_indices"] = child_indices
                    chunks.append(chunk_dict)
                    chunks.extend(child_chunk_dicts)
                    chunk_index += 1
                    continue
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
        except _PROGRAMMING_ERRORS:
            raise
        except Exception as exc:  # noqa: BLE001
            saltados.append(
                {
                    "page_number": block.get("page_number"),
                    "heading_path": block.get("heading_path"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            logger.warning(
                "chunking_block_skipped",
                correlation_id=str(correlation_id),
                document_id=str(document_id),
                heading_path=block.get("heading_path"),
                page_number=block.get("page_number"),
                error=str(exc),
            )
            continue

    if saltados:
        logger.error(
            "chunking_blocks_skipped_total",
            correlation_id=str(correlation_id),
            document_id=str(document_id),
            bloques_saltados=len(saltados),
            bloques_totales=len(intermediate),
            paginas=sorted({s["page_number"] for s in saltados if s["page_number"] is not None}),
            errores=sorted({s["error"] for s in saltados})[:5],
            impact="el documento quedó indexado sin esos bloques",
        )

    logger.info(
        "chunking_completed",
        correlation_id=str(correlation_id),
        document_id=str(document_id),
        total_chunks=len(chunks),
        bloques_saltados=len(saltados),
    )
    return chunks
