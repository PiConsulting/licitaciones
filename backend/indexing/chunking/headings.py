"""Deteccion, fusion y normalizacion de encabezados (multi-pagina, truncados, numerados/decimales, boilerplate repetido)."""
from __future__ import annotations

import re
from collections import defaultdict

import structlog

logger = structlog.get_logger(__name__)

_BOILERPLATE_MIN_PAGES = 3
_BOILERPLATE_MIN_PAGE_FRACTION = 0.5
_INCISO_MIN_SUBSTANTIVE_CHARS = 100
_INCISO_PATTERN = re.compile(
    r"^(?P<label>[a-z]\)|[ivxIVX]+\)|[0-9]+[.)])\s+(?P<text>.+)",
    re.MULTILINE,
)
_RUN_IN_HEADING_RE = re.compile(
    r"^(?P<label>"
    r"(?:art[ií]culo|art\.)\s*(?:n\s*[°ºo]?\s*)?\d+[a-z]?"  # "Artículo 10", "Art. 5a"
    r"|\d{1,2}(?:\.\d{1,2})*"  # "10", "5.2", "3.1.2"
    r")"
    r"\s*[:.\-–)]?\s+"  # Separador después del label (opcional: ":", ".", "-", ")")
    r"(?:"
    # Caso con ":" propio del título (ej. "Artículo 10: GARANTÍA DE
    # ADJUDICACIÓN: En caso de corresponder..."): el título es TODO lo que
    # hay hasta ese ":", sin importar cuánto mida -- antes esta rama no
    # existía y la única alternativa (title_bare, no-greedy) se conformaba
    # con las primeras 2-3 letras ("GAR") porque nada la obligaba a seguir.
    r"(?P<title_colon>[A-ZÁÉÍÓÚÑ][^\n:]{1,89}):\s*(?=\S)"
    r"|"
    # Caso sin ":" propio (ej. "Artículo 5. Objeto de la contratación..."):
    # no hay delimitador que marque dónde termina el título, así que se
    # mantiene el comportamiento original (no-greedy, mínimo 3 chars) --
    # `_looks_like_section_title` filtra lo que quede demasiado corto o en
    # minúsculas.
    r"(?P<title_bare>[A-ZÁÉÍÓÚÑ][^\n]{2,90}?)(?:\s*[:.])?"
    r")",
    re.IGNORECASE,
)


def _run_in_title(match: re.Match) -> str:
    """Título capturado por `_RUN_IN_HEADING_RE`, sea cual sea la rama que matcheó."""
    return match.group("title_colon") or match.group("title_bare") or ""
_MIN_RUN_IN_TITLE_LETTERS = 3
_BOILERPLATE_EDGE_CHARS = " -–—:|.,"
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
_HEADING_TAIL_MAX_CHARS = 90
_DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+\S")
_TOP_LEVEL_DIVISION_RE = re.compile(r"^(?:anexo|ap[eé]ndice)\b", re.IGNORECASE)


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


def _normalize_heading_value(text: str) -> str:
    return " ".join(text.strip().split())


# Marcadores de lista / artefactos de parseo que Document Intelligence a veces
# etiqueta como encabezado (trae `heading_level`) pero que NO son titulos de
# seccion: vinetas ("·", "•", "o ", "- "), "ITEM N", columnas ("col_3"),
# checkbox ("☐"). Si se apilan en `heading_stack` contaminan el `heading_path`
# de todo lo que cuelga debajo (y con el la clasificacion por encabezado).
_BULLET_MARKER_HEADING_RE = re.compile(
    r"^\s*(?:o\s|[·•▪◦‣]|[-*]\s|item\s*\d|col_\d|[☐□❑])",
    re.IGNORECASE,
)


def _is_bullet_marker_heading(text: object) -> bool:
    """True si el texto parece una vineta / fila / artefacto, no un titulo."""
    return bool(_BULLET_MARKER_HEADING_RE.match(str(text or "")))


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
            title = _run_in_title(match).strip() if match else ""
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
