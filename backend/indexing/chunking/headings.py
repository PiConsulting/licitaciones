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
    # Matchea también notación ordinal ("10º", "8°"); sin esto, cláusulas así
    # ("8º.- I.V.A.") no se promovían a heading y contaminaban el inciso de la
    # cláusula anterior vía `_detect_incisos` (bug real, ver fase1-mapeo-pipeline-2026-09-14.md).
    r"|\d{1,2}(?:\.\d{1,2})*[°º]?"  # "10", "5.2", "3.1.2", "10º", "8°"
    r")"
    # La rama ".-" va ANTES que la clase de un solo carácter: "Nº.- TÍTULO"
    # (punto y guion juntos) es la convención más común en pliegos argentinos.
    r"\s*(?:\.-|[:.\-–)])?\s+"  # Separador después del label (".-", o uno de ":", ".", "-", ")")
    r"(?:"
    # Título hasta su propio ":" (ej. "Artículo 10: GARANTÍA DE ADJUDICACIÓN: ...").
    r"(?P<title_colon>[A-ZÁÉÍÓÚÑ][^\n:]{1,89}):\s*(?=\S)"
    r"|"
    # Sin ":" propio: no-greedy, mínimo 3 chars; `_looks_like_section_title` filtra el resto.
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
_ROMAN_NUMERAL_RE = re.compile(r"^[IVXLCDM]+$", re.IGNORECASE)
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
# Capitulo numerado ("1. OBJETO", "Articulo 16. GARANTIAS"), con o sin la
# palabra "Articulo"/"Art." antes del numero. Compartido por
# _normalize_numbered_heading_levels (hermanos entre si) y
# _nest_unnumbered_headings_under_numbered (evitar anidarlos mal).
_CHAPTER_NUMBER_RE = re.compile(
    r"^(?:art[ií]culo\s*n?[º°]?\.?\s*|art\.\s*n?[º°]?\.?\s*)?(\d+)[.:]\s+[A-ZÁÉÍÓÚÑ]",
    re.IGNORECASE,
)


def _chapter_number(content: object) -> int | None:
    match = _CHAPTER_NUMBER_RE.match(str(content or "").strip())
    return int(match.group(1)) if match else None


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


# DI a veces etiqueta vinetas/"ITEM N"/columnas/checkbox como heading; si se
# apilan en heading_stack contaminan el heading_path de todo lo que cuelga debajo.
_BULLET_MARKER_HEADING_RE = re.compile(
    r"^\s*(?:o\s|[·•▪◦‣]|[-*]\s|item\s*\d|col_\d|[☐□❑])",
    re.IGNORECASE,
)

# Sello de version/revision de plantilla ("V 1.13", "Rev. 3"); caso real:
# PLIEGO_5443-26 lo promovía a heading huérfano sin cuerpo propio.
_VERSION_STAMP_RE = re.compile(
    r"^\s*(?:v|ver|vers(?:i[oó]n)?|rev(?:isi[oó]n)?)\.?\s*\d+(?:\.\d+)*\s*$",
    re.IGNORECASE,
)


def _is_bullet_marker_heading(text: object) -> bool:
    """True si el texto parece una vineta / fila / artefacto / sello de
    version, no un titulo."""
    valor = str(text or "")
    return bool(_BULLET_MARKER_HEADING_RE.match(valor)) or bool(_VERSION_STAMP_RE.match(valor))


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


def _extend_title_with_uppercase_words(title: str, resto: str) -> tuple[str, str]:
    """Extiende un `title_bare` (capturado no-greedy por `_RUN_IN_HEADING_RE`)
    con las palabras en MAYÚSCULAS que le siguen inmediatamente, cuando el
    corte lazy del regex se detuvo demasiado pronto.

    Caso real (Rosario): en "ARTÍCULO 12: PLAZO DE ENTREGA El plazo de
    entrega..." la rama `title_bare` (no-greedy, sin límite de mayúsculas
    real) se conforma con "PLA" -- ya cumple `_looks_like_section_title`
    (3 letras, 100% mayúsculas) y el regex no tiene ninguna razón para seguir.
    El límite real del título en un pliego argentino es la propia tipografía:
    sigue en mayúsculas hasta la primera palabra que NO lo es (aquí "El",
    que arranca la oración del cuerpo). Esto reconstruye ese límite real
    -- incluyendo el caso de palabra partida a la mitad ("PLA" + "ZO" sin
    espacio real entre ambas, que se unen sin insertar uno).

    Acotado a `_HEADING_TAIL_MAX_CHARS` en total para no devorar un párrafo
    entero si el pliego escribe una cláusula completa en mayúsculas (caso
    real distinto, no un título cortado).
    """
    while resto and len(title) < _HEADING_TAIL_MAX_CHARS:
        match = re.match(r"^(\s*)(\S+)", resto)
        if not match:
            break
        leading_ws, palabra = match.group(1), match.group(2)
        candidato = palabra.rstrip(":.")
        if not candidato or not _is_upper_run(candidato):
            break
        title = f"{title} {palabra}" if leading_ws else f"{title}{palabra}"
        resto = resto[match.end() :]
    return title, resto


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

            raw_resto = stripped[match.end() :]
            # Chequeado ANTES de _extend_title_with_uppercase_words a propósito:
            # esa extensión puede consumir legítimamente TODO el remanente cuando
            # el título ocupa el bloque entero (el cuerpo real está en otro bloque).
            if not raw_resto.strip():
                pending.append(stripped)
                continue

            title, resto = _extend_title_with_uppercase_words(title, raw_resto)
            body = resto.strip()

            flush_pending()

            heading_block = dict(block)
            heading_block["content"] = f"{match.group('label').strip()}: {title}"

            heading_block["heading_level"] = 2
            heading_block.pop("table_ref", None)
            emitted.append(heading_block)

            if body:
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
    presente); un parrafo de cuerpo repetido no entra en este chequeo.

    Ademas incluye, sin depender de frecuencia, cualquier heading marcado
    `is_confirmed_page_furniture` (`markdown_parsing._collect_page_header_footer_texts`):
    ese mismo texto ya aparecio en otra pagina del documento como comentario
    `PageHeader`/`PageFooter` de Document Intelligence -- la propia DI
    confirmando que es membrete, aunque en ESTA ocurrencia se haya colado
    como heading real. Caso real: Nucleoelectrica, donde el membrete queda
    invisible (descartado como comentario) en la mayoria de las paginas y
    nunca cruza el umbral de frecuencia por si solo."""
    confirmados = {
        _normalize_heading_value(str(block.get("content", ""))).lower()
        for block in blocks
        if block.get("heading_level") is not None and block.get("is_confirmed_page_furniture")
    }
    confirmados.discard("")

    total_pages = len({int(block["page_number"]) for block in blocks}) or 1
    if total_pages < min_pages:
        return confirmados

    pages_by_heading: dict[str, set[int]] = defaultdict(set)
    for block in blocks:
        if block.get("heading_level") is None:
            continue
        normalized = _normalize_heading_value(str(block.get("content", ""))).lower()
        if normalized:
            pages_by_heading[normalized].add(int(block["page_number"]))

    threshold = max(min_pages, int(total_pages * min_page_fraction))
    por_frecuencia = {text for text, pages in pages_by_heading.items() if len(pages) >= threshold}
    return por_frecuencia | confirmados


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
                and not first_word_next[-1] in ".,:;"
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
                and len(first_word_next) < 6
            )

            is_fragmented = (
                next_starts_lowercase or next_starts_with_short_fragment or likely_continuation
            )

            if is_fragmented:
                merged_content = _join_split_heading(content, next_content)
                merged_block = {**block}
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


def _heading_last_token_looks_truncated(heading_text: str) -> bool:
    """¿La última palabra del heading es una tirada corta en mayúsculas que
    parece cortada ("PLA", "GAR"), no una palabra corta pero completa
    ("ANEXO IV", "TÍTULO II", "EL")?

    Sin bbox (no comparable entre páginas distintas) esta es la única señal
    para decidir si vale la pena buscar la cola de este heading en la página
    siguiente -- un heading que ya se ve completo ("DOCUMENTACIÓN A
    PRESENTAR") nunca debe disparar la búsqueda, para no fusionar por error
    con un párrafo nuevo que sencillamente empieza con una palabra corta en
    mayúsculas seguida de ":" (ej. "NOTA: Se informa que...").
    """
    words = heading_text.split()
    if not words:
        return False
    last = words[-1]
    if last.upper() in _PALABRAS_CORTAS_COMPLETAS or _ROMAN_NUMERAL_RE.match(last):
        return False
    return _is_upper_run(last) and len(last) <= _SPLIT_WORD_MAX_CHARS


def _merge_truncated_headings_across_pages(blocks: list[dict]) -> list[dict]:
    """Reconstruye un heading cortado justo en el salto de página, cuando
    Document Intelligence etiquetó la cola como párrafo (no como heading) en
    la página siguiente -- caso real detectado en el pliego de Rosario:

        heading (pág. 4)  "ARTÍCULO 12: PLA"
        párrafo (pág. 5)  "ZO DE ENTREGA"

    `_merge_split_headings_across_pages` no lo cubre porque exige que la
    cola TAMBIÉN tenga `heading_level`; `_merge_truncated_headings_with_body`
    tampoco, porque exige la misma página (usa bbox, que no es comparable
    entre páginas). La guarda acá es que el heading ORIGINAL tiene que verse
    cortado (`_heading_last_token_looks_truncated`) -- así un heading ya
    completo nunca dispara la fusión, aunque el párrafo de la página
    siguiente empiece con una palabra corta en mayúsculas + ":".
    """
    merged: list[dict] = []
    skip_indexes: set[int] = set()

    for index, block in enumerate(blocks):
        if index in skip_indexes:
            continue

        content = str(block.get("content", "")).strip()
        if (
            block.get("heading_level") is None
            or index + 1 >= len(blocks)
            or not _heading_last_token_looks_truncated(content)
        ):
            merged.append(block)
            continue

        body = blocks[index + 1]
        if (
            body.get("heading_level") is not None
            or body.get("block_type") == "table"
            or int(body.get("page_number", -1)) != int(block.get("page_number", -2)) + 1
        ):
            merged.append(block)
            continue

        split = _split_heading_tail(str(body.get("content", "")))
        if split is None:
            merged.append(block)
            continue

        tail, remaining_body = split
        heading_block = dict(block)
        heading_block["content"] = _join_heading_tail(content, tail)
        merged.append(heading_block)

        logger.info(
            "merged_truncated_heading_across_pages",
            page=block.get("page_number"),
            heading_before=content[:60],
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

    FIX (auditoría de chunking, hallazgo real sobre el PUBCG de Santa Fe): la
    version anterior RESETEABA `current_sequence`/`expected_number` ante
    CUALQUIER heading que no matcheara "N. TÍTULO" -- y eso es prácticamente
    TODO heading real entre dos capítulos consecutivos (sub-secciones tipo
    "1.1.", "1.2.", divisores sin número, etc). En la práctica la función
    nunca lograba encadenar dos capítulos reales porque siempre hay
    sub-headings en el medio: la secuencia se reseteaba antes de llegar al
    capítulo siguiente. Confirmado en Santa Fe: "2. DE LA CONVOCATORIA" y "8.
    Penalidades y Sanciones" quedaban en un nivel de heading más profundo que
    sus hermanos (1, 3, 4, 5, 6, 7, 9, 10, 11) -- Azure DI les asignó un
    tamaño de fuente distinto en el PDF -- y como la normalización nunca los
    alcanzaba, quedaban anidados como si fueran sub-sección del capítulo
    ANTERIOR (heading_path incorrecto para todo lo que colgaba debajo) y
    generaban un chunk-solo-título huérfano al cerrarse sin haber recibido
    nunca su propio cuerpo.

    Ahora un heading que no matchea "N. TÍTULO" (sub-sección, divisor sin
    número) simplemente se IGNORA -- no rompe la secuencia en curso, la
    dejamos seguir esperando el próximo capítulo. Solo se resetea la
    secuencia cuando aparece un "N." que rompe el orden esperado Y no es un
    reinicio legítimo (otro "1.", ej. un anexo con su propia numeración desde
    cero).

    FIX 2 (auditoría de chunking, hallazgo real: Pliego del Tribunal Superior
    de Justicia): "N. TÍTULO" exigía que el numero fuera LO PRIMERO del
    heading, asi que la misma convención con "Artículo"/"Art." antes del
    número ("Artículo 16. GARANTÍAS", "ARTÍCULO 9: ADJUDICACIÓN") nunca
    entraba a la secuencia -- ver `_chapter_number`/`_CHAPTER_NUMBER_RE`.
    """
    logger.info(
        "normalize_function_called",
        total_blocks=len(blocks),
    )

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
        number = _chapter_number(content)

        if number is None:
            # No es parte de la secuencia de capítulos, pero tampoco la interrumpe.
            continue

        if number == expected_number:
            current_sequence.append(i)
            expected_number += 1
            logger.info("sequence_item_added", index=i, number=number, content=content[:60])
        elif number == 1:
            if len(current_sequence) >= 2:
                sequences.append(current_sequence)
                logger.info("sequence_completed_new_start", length=len(current_sequence))
            current_sequence = [i]
            expected_number = 2
        else:
            # No matchea lo esperado y no es un reinicio legítimo (otro "1."):
            # probablemente ruido, se ignora sin resetear la secuencia en curso.
            logger.info("sequence_item_ignored_out_of_order", index=i, number=number, content=content[:60])

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
        # "Artículo N. TÍTULO" SÍ está numerado (_chapter_number); tratarlo como
        # heading "sin numerar" acá deshace el fix de _normalize_numbered_heading_levels.
        if (
            _decimal_heading_depth(contenido) is not None
            or _TOP_LEVEL_DIVISION_RE.match(contenido)
            or _chapter_number(contenido) is not None
        ):
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
