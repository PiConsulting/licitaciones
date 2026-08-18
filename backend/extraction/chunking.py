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

# PARENT/CHILD CHUNKING (auditoría 2026-08-12, US-3.1): a partir de cuántos
# caracteres un chunk conviene subdividir en incisos -- ver
# `_bmad-output/parent-child-chunking-implementation.md`. Por debajo de esto
# el chunk ya es lo bastante chico como para que subdividir no aporte
# precisión y sí sume overhead de storage/retrieval.
_PARENT_CHILD_MIN_CHARS = 800
# Un inciso detectado por debajo de este largo probablemente sea un falso
# positivo del regex (ej. una enumeración corta que no es jurídicamente
# subdividible) -- en ese caso es más seguro no partir que partir mal, así
# que `_detect_incisos` aborta toda la subdivisión del chunk.
_INCISO_MIN_SUBSTANTIVE_CHARS = 100

# Incisos tipo "a)", "b)", "i)", "ii)", "1.", "2)" al inicio de línea.
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

# Cantidad de terminos distintos del glossary a partir de la cual el score de
# una categoria se considera saturado (1.0). Independiente de cuantos sinonimos
# tenga cargada cada categoria.
_KEYWORD_SCORE_SATURATION = 4
# CHK-08: a partir de cuántos matches por cada 100 palabras se considera que un
# chunk es "máximamente denso". Estaba implícito en la unidad de la división
# (1 match cada 100 palabras), y con ese valor cualquier chunk de menos de 100
# palabras satura con un solo match: un párrafo corto o una fila de tabla que
# menciona UNA vez "anexo" alcanza `_DEFAULT_PRIMARY_THRESHOLD`.
#
# Se conserva el valor actual a propósito: subirlo cambia qué chunks pasan el
# umbral, y eso es calibración, no un arreglo. Necesita el set de chunks
# etiquetados. Queda con nombre para que ese día haya un solo lugar que tocar.
_DENSITY_SATURATION_PER_100_WORDS = 1.0
# Threshold por defecto para categorías sin configuración explícita
_DEFAULT_PRIMARY_THRESHOLD = 0.25
_DEFAULT_SECONDARY_THRESHOLD = 0.12

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

    FIX CRÍTICO (auditoría 2026-08-13, hallazgo CHK-01): el carry de overlap
    tenía dos defectos que se combinaban para producir chunks de hasta 2x
    `chunk_size` con duplicación total del contenido:

      1. `if carried and carried_tokens + prev_tokens > overlap` -- por el
         `carried and`, el PRIMER párrafo se arrastraba siempre, sin importar
         su tamaño. Con párrafos de 690 tokens y overlap de 120, el "overlap"
         terminaba siendo un párrafo entero de 690.
      2. Después del carry se hacía `current.append(paragraph)` sin volver a
         validar el límite, así que el chunk resultante era carry + el párrafo
         que justamente había disparado el flush por no entrar.

    Reproducido con los defaults (chunk_size=700, overlap=120) sobre 3
    párrafos de 690 tokens: salían chunks de 690, 1380 y 1380 tokens, con el
    chunk 0 contenido ÍNTEGRAMENTE dentro del chunk 1 (2070 tokens de entrada
    -> 3450 emitidos, 67% de redundancia). Eso inflaba el índice, gastaba
    slots de top_k en texto repetido y disparaba el bonus de "dato consistente
    en múltiples fragmentos" del prompt del sistema.

    Ahora el presupuesto de carry es `min(overlap, chunk_size - len(tokens))`,
    que garantiza por construcción que el chunk siguiente entra completo, y no
    se arrastra ningún párrafo que por sí solo exceda ese presupuesto.

    NOTA sobre el overlap resultante: como los párrafos son atómicos (nunca se
    cortan), cuando un párrafo es más grande que `overlap` el solapamiento
    entre chunks consecutivos pasa a ser CERO. Eso es correcto y no pierde
    información: el overlap existe para que un hecho que cae sobre el borde de
    un chunk aparezca entero en alguno, y acá ningún hecho puede caer sobre un
    borde -- cada párrafo está completo en exactamente un chunk. El overlap
    real sigue aplicándose donde sí hace falta: en `_split_with_overlap`, que
    es el único punto donde se parte texto por el medio.
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

            # Presupuesto de arrastre: nunca más que `overlap`, y nunca tanto
            # como para que el párrafo que viene no entre en el chunk nuevo.
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

    Nota (actualizado tras fix de auditoria 2026-08-12, hallazgo C-2):
    `_parse_markdown_blocks` ahora SI hace flush de parrafo en cada linea en
    blanco, asi que en el caso normal cada bloque de cuerpo ya corresponde a
    un unico parrafo real (precondicion que necesita `_enrich_blocks_with_para_id`
    para asignar el bbox correcto por indice posicional). Aun asi, esta funcion
    sigue soportando bloques con multiples segmentos separados por `\\n\\n`
    como caso residual (por ejemplo bloques ya fusionados aguas arriba, o
    fixtures/tests antiguos), por lo que se sigue mirando el inicio de cada
    segmento interno y no solo el inicio del bloque."""
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


# Cuánto puede medir el pedazo de una palabra que Document Intelligence dejó a
# cada lado del salto de página. "PLA" + "ZO": tiradas cortas y en mayúsculas.
# Una palabra completa de un título rara vez es tan corta y, si lo es ("DE",
# "LA"), la unión con espacio es igualmente correcta.
_SPLIT_WORD_MAX_CHARS = 5

# Palabras cortas y completas del castellano. Un token del borde que esté acá
# NO es el pedazo de una palabra partida, por más corto y en mayúsculas que
# esté: "CAPÍTULO II — DE LAS" + "OBLIGACIONES…" tiene que unirse con espacio.
_PALABRAS_CORTAS_COMPLETAS = {
    "EL", "LA", "LO", "LOS", "LAS", "UN", "UNA", "UNOS", "UNAS",
    "DE", "DEL", "AL", "A", "EN", "Y", "O", "U", "POR", "CON", "SIN",
    "SU", "SUS", "ES", "SE", "NO", "SI", "QUE", "PARA", "SOBRE",
}


def _join_split_heading(current: str, following: str) -> str:
    """Une las dos mitades de un encabezado partido entre páginas.

    Sin espacio SÓLO si lo que se partió fue una palabra; con espacio si lo que
    se partió fue el título en dos renglones. La diferencia se decide por la
    forma de los tokens del borde, no por el vocabulario: un pedazo de palabra
    queda como una tirada corta en mayúsculas, y a los dos lados del corte hay
    letras (no puntuación ni dígitos).
    """
    izquierda = str(current or "").rstrip()
    derecha = str(following or "").lstrip()
    if not izquierda:
        return derecha
    if not derecha:
        return izquierda

    ultimo = izquierda.split()[-1]
    primero = derecha.split()[0]

    # Un pedazo puede quedar de cualquiera de los dos lados, y el de la derecha
    # puede venir en minúscula ("DOCUMEN" + "tación") o en mayúscula ("PLA" +
    # "ZO"). Lo que NUNCA es un pedazo es una palabra corta y completa.
    completa_izquierda = ultimo.upper() in _PALABRAS_CORTAS_COMPLETAS
    completa_derecha = primero.upper() in _PALABRAS_CORTAS_COMPLETAS

    pedazo_izquierdo = (
        not completa_izquierda
        and _is_upper_run(ultimo)
        and len(ultimo) <= _SPLIT_WORD_MAX_CHARS
    )
    pedazo_derecho = not completa_derecha and (
        (_is_upper_run(primero) and len(primero) <= _SPLIT_WORD_MAX_CHARS)
        or primero[0].islower()
    )

    palabra_partida = (
        izquierda[-1].isalpha()
        and derecha[0].isalpha()
        # Si la izquierda termina en una palabra corta y completa, el corte no
        # cayó dentro de una palabra: "3.1. Plataforma de" + "software…".
        and not completa_izquierda
        and (pedazo_izquierdo or pedazo_derecho)
    )

    return f"{izquierda}{derecha}" if palabra_partida else f"{izquierda} {derecha}"


def _merge_split_headings_across_pages(blocks: list[dict]) -> list[dict]:
    """Detecta y fusiona encabezados que Document Intelligence partió entre páginas.
    
    Problema típico:
    - Página N: "ARTÍCULO 12: PLA" (heading_level=2)
    - Página N+1: "ZO DE ENTREGA" (heading_level=2)
    
    Solución:
    - Detectar headings fragmentados por análisis de ambas partes
    - Fusionar contenido: "ARTÍCULO 12: PLAZO DE ENTREGA"
    - Mantener metadata del primer bloque (para bbox correcto)
    """
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
        
        # Verificar si este heading puede estar partido
        content = str(block.get("content", "")).strip()
        next_block = blocks[i + 1]
        next_level = next_block.get("heading_level")
        next_content = str(next_block.get("content", "")).strip()
        
        # Condiciones para fusión:
        # 1. Ambos son headings del mismo nivel
        # 2. Están en páginas consecutivas
        
        if (next_level == level and 
            int(next_block["page_number"]) == int(block["page_number"]) + 1):
            
            # Analizar ambas partes para detectar fragmentación
            words_current = content.split()
            words_next = next_content.split()
            
            if not words_current or not words_next:
                merged.append(block)
                continue
            
            last_word_current = words_current[-1]
            first_word_next = words_next[0]
            
            # CASOS DE NO FRAGMENTACIÓN (false positives a evitar):
            # - Números romanos: "ANEXO I" + "ANEXO II"
            # - Headings completos: "CAPÍTULO 1" + "CAPÍTULO 2"
            
            is_roman_current = bool(re.match(r'^[IVXLCDM]+$', last_word_current, re.IGNORECASE))
            is_roman_next = bool(re.match(r'^[IVXLCDM]+$', first_word_next, re.IGNORECASE))
            
            # Patrones de FRAGMENTACIÓN REAL:
            # 1. Siguiente empieza con minúscula → continuación obvia
            # 2. Primera palabra del siguiente es muy corta (< 4 chars) y mayúscula → fragmento ("ZO")
            # 3. Patrón "ARTÍCULO N: ABC" + "DEF..." donde DEF completa ABC
            
            next_starts_lowercase = first_word_next[0].islower()
            
            next_starts_with_short_fragment = (
                len(first_word_next) < 4 and 
                first_word_next.isupper() and 
                not is_roman_next and
                not first_word_next[-1] in ".,:;"  # No es abreviación
            )
            
            # Patrón adicional: si el heading actual termina con ":" o keywords
            # y la parte siguiente NO empieza con palabra típica de inicio
            current_ends_with_colon = last_word_current.endswith(':')
            next_starts_with_article = first_word_next.upper() in ['EL', 'LA', 'LOS', 'LAS', 'DE', 'DEL']
            
            likely_continuation = (
                current_ends_with_colon and 
                not next_starts_with_article and
                len(first_word_next) < 6  # Fragmento corto después de ":"
            )
            
            is_fragmented = (
                next_starts_lowercase or 
                next_starts_with_short_fragment or
                likely_continuation
            )
            
            if is_fragmented:
                # FIX (auditoría 2026-08-13, hallazgo CHK-09): antes esto era
                # siempre `content + next_content`, sin espacio. Para el caso
                # que motivó la función ("ARTÍCULO 12: PLA" + "ZO DE ENTREGA")
                # eso es correcto, porque DI partió una PALABRA. Pero el
                # disparador `next_starts_lowercase` se activa también cuando lo
                # que DI partió es un TÍTULO en dos renglones tipográficos, que
                # es frecuente: página N "5. GARANTÍAS", página N+1 "de
                # cumplimiento de contrato". Ahí la concatenación sin espacio
                # producía "5. GARANTÍASde cumplimiento de contrato".
                #
                # El token "garantiasde" no existe. `_classify_by_heading` lo
                # sobrevive de casualidad, porque busca "garantia" por
                # substring y sigue siendo prefijo -- pero el `title` que va al
                # embedding y al campo searchable del índice queda corrupto, y
                # `_normalize_heading_value` no lo arregla.
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


# Largo máximo de la cola de un título que quedó pegada al cuerpo. Un título
# de artículo de pliego no pasa de una línea; más que esto ya es cuerpo.
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

    # Caso (b): todo el bloque es cola de título.
    if "\n" not in stripped and len(stripped) <= _HEADING_TAIL_MAX_CHARS and _is_upper_run(stripped):
        return stripped, ""

    # Caso (a): cola terminada en ':' seguida del cuerpo.
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
    # Una palabra cortada deja un fragmento corto y en mayúsculas pegado al
    # final del encabezado; un título completo termina en palabra entera.
    looks_truncated = (
        heading_text[-1].isalpha()
        and tail[0].isalpha()
        and _is_upper_run(last_token)
        and len(last_token) <= 5
    )
    return f"{heading_text}{tail}" if looks_truncated else f"{heading_text} {tail}"


def _merge_truncated_headings_with_body(blocks: list[dict]) -> list[dict]:
    """Reconstruye los encabezados que Document Intelligence cortó al medio.

    FIX (auditoría 2026-08-13): sobre un pliego real de la Municipalidad de
    Rosario, DI emitió el encabezado "Artículo Nº 10: GAR" y arrancó el párrafo
    siguiente con "ANTÍA DE ADJUDICACIÓN: En caso de corresponder, el importe de
    las garantías de la contratación...". Ni el título ni el cuerpo contenían la
    palabra "garantía", así que ese artículo era invisible para BM25 y para el
    vector, y la categoría `garantias` respondió `not_applicable` -- "el pliego
    sólo prevé garantía técnica del equipamiento, ninguna financiera" -- sobre un
    pliego cuyo Artículo 10 se titula GARANTÍA DE ADJUDICACIÓN. El usuario
    recibía información legal equivocada, no un resaltado corrido.

    `_merge_split_headings_across_pages` no cubre este caso porque exige que las
    dos mitades sean encabezados en páginas CONSECUTIVAS; acá la segunda mitad
    es un párrafo de cuerpo en la MISMA página.

    La detección es estructural, no léxica: se exige que el cuerpo empiece en la
    misma línea visual que el encabezado (ver `_starts_on_same_line`). Si el
    bloque no tiene bbox utilizable no se fusiona nada -- preferimos no tocar el
    encabezado antes que fusionar por una coincidencia de mayúsculas.
    """
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
        # Si no queda cuerpo, el bloque siguiente era pura cola de título: ya
        # se absorbió en el encabezado y no se emite por separado.
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
    
    # Patron para detectar headings numerados: "1. TITULO", "2. TITULO", etc.
    # IMPORTANTE: El .* al final permite cualquier texto después de la mayúscula inicial
    numbered_pattern = re.compile(r'^(\d+)\.\s+[A-ZÁÉÍÓÚÑ].*', re.IGNORECASE)
    
    # Log para debugging
    headings_found = [
        (i, block.get("heading_level"), block.get("content", "")[:60])
        for i, block in enumerate(blocks)
        if block.get("heading_level") is not None
    ]
    if headings_found:
        logger.info("normalize_scan_start", total_headings=len(headings_found))
        # Log el contenido de cada heading para diagnosticar
        for idx, level, content in headings_found[:10]:
            logger.info("heading_content", index=idx, level=level, content=content)
    
    # Agrupar headings por secuencias numericas consecutivas
    sequences: list[list[int]] = []  # indices de blocks que forman secuencia
    current_sequence: list[int] = []
    expected_number = 1
    
    for i, block in enumerate(blocks):
        level = block.get("heading_level")
        if level is None:
            # No es heading, CONTINUAR sin resetear (permite párrafos entre headings numerados)
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
                # Número no consecutivo, guardar secuencia actual si existe
                if len(current_sequence) >= 2:
                    sequences.append(current_sequence)
                    logger.info("sequence_completed_non_consecutive", length=len(current_sequence))
                # Empezar nueva secuencia si es "1.", sino descartar
                current_sequence = [i] if number == 1 else []
                expected_number = 2 if number == 1 else 1
        else:
            # Heading no numerado, guardar secuencia actual y resetear
            if len(current_sequence) >= 2:
                sequences.append(current_sequence)
                logger.info("sequence_completed_non_numbered", length=len(current_sequence))
            current_sequence = []
            expected_number = 1
    
    # Capturar última secuencia si quedó pendiente
    if len(current_sequence) >= 2:
        sequences.append(current_sequence)
    
    # Normalizar niveles dentro de cada secuencia al mínimo nivel
    normalized = blocks.copy()
    for sequence_indices in sequences:
        # Encontrar el nivel mínimo (más alto en jerarquía) de la secuencia
        min_level = min(normalized[i]["heading_level"] for i in sequence_indices)
        
        # Normalizar todos al mismo nivel
        for i in sequence_indices:
            normalized[i] = {**normalized[i], "heading_level": min_level}
            
        logger.info(
            "normalized_heading_sequence",
            indices=sequence_indices,
            target_level=min_level,
            headings=[normalized[i]["content"][:50] for i in sequence_indices[:5]],
        )
    
    return normalized


# El punto final es obligatorio: sin él, "1 Plataforma de software" -- la
# columna Ítem de una planilla -- contaría como encabezado numerado.
_DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+\S")


def _decimal_heading_depth(content: object) -> int | None:
    """Profundidad que el propio encabezado declara: `1.` → 1, `3.1.2.` → 3."""
    texto = str(content or "").strip().replace("\\", "")
    match = _DECIMAL_HEADING_RE.match(texto)
    return len(match.group(1).split(".")) if match else None


def _normalize_decimal_heading_levels(blocks: list[dict]) -> list[dict]:
    """El nivel de un encabezado decimal lo dice su numeración, no Azure DI.

    FIX (auditoría 2026-08-14, hallazgo CHK-16):
    `_normalize_numbered_heading_levels` sólo reconoce `^(\\d+)\\.\\s+[A-Z…]`, que
    matchea "1. Generalidades" pero **no** "1.6.", "3.1.1." ni "5.3.". O sea, no
    tocaba ningún encabezado decimal -- que es toda la numeración del PET de
    Bancor.

    Consecuencia medida: el `section_path` del chunk 12 salió
    `… > 1. Generalidades > 1.6. Visita técnica obligatoria > 1.7. Plazo de
    entrega`. `1.6` y `1.7` son hermanos, no padre e hijo. Ese path alimenta el
    `section_hint` que desambigua los resaltados y el contexto que ve el
    redactor de la síntesis, así que una jerarquía inventada se propaga a las
    dos puntas.

    Un pliego que numera sus secciones está DECLARANDO la jerarquía: "3.1.2."
    dice, sin ambigüedad, que cuelga de "3.1", que cuelga de "3". Eso le gana a
    lo que DI haya inferido del tamaño de la tipografía.

    Sólo se tocan los de profundidad ≥ 2. Los de primer nivel los sigue
    manejando `_normalize_numbered_heading_levels`, que además usa la
    consecutividad como señal.
    """
    profundidades: list[tuple[int, int]] = []
    for indice, block in enumerate(blocks):
        if block.get("heading_level") is None:
            continue
        profundidad = _decimal_heading_depth(block.get("content"))
        if profundidad is not None:
            profundidades.append((indice, profundidad))

    if not any(profundidad >= 2 for _, profundidad in profundidades):
        return blocks

    # El nivel de referencia es el que ya tienen los encabezados de primer
    # nivel; si el pliego no tiene ninguno, se deduce del decimal más chico.
    niveles_raiz = [int(blocks[i]["heading_level"]) for i, p in profundidades if p == 1]
    if niveles_raiz:
        base = min(niveles_raiz)
    else:
        profundidad_min = min(p for _, p in profundidades)
        base = min(int(blocks[i]["heading_level"]) for i, p in profundidades if p == profundidad_min)
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


# Divisiones que un pliego numerado igual pone al mismo nivel que sus secciones
# numeradas: el anexo no "cuelga" del último artículo, es su hermano. Es la
# única excepción conocida a la regla de `_nest_unnumbered_headings_under_numbered`
# y está sostenida por los dos pliegos analizados (Rosario tiene "ANEXO I"/"ANEXO
# II" consecutivos; ver `test_merge_split_headings.py`).
_TOP_LEVEL_DIVISION_RE = re.compile(r"^(?:anexo|ap[eé]ndice)\b", re.IGNORECASE)


def _nest_unnumbered_headings_under_numbered(blocks: list[dict]) -> list[dict]:
    """Un encabezado sin numerar que aparece después de uno numerado cuelga de él.

    FIX (auditoría 2026-08-14, hallazgo CHK-19): con CHK-16 puesto, los
    encabezados numerados quedan en el nivel que declara su numeración, pero los
    **no numerados** siguen en el nivel que les puso Azure DI -- y DI se lo
    asigna por tipografía, no por jerarquía. En el PET de Bancor las subsecciones
    en viñeta de 3.1.8 (`Capa de infraestructura y virtualización (VCF)`,
    `Resiliencia y backup seguro`, `· Equipo Principal de Almacenamiento de
    BackUp`) salían en nivel 2, o sea el MISMO que `3. Especificaciones
    técnicas`. Y un encabezado de nivel 2 hace `pop_to_level(2)`: se lleva
    puestos a `3.`, `3.1.` y `3.1.8.` de una.

    Medido sobre el reanálisis, ya con CHK-17 aplicado: el chunk 34 salió
    `PLIEGO DE ESPECIFICACIONES TÉCNICAS > Capa de infraestructura y
    virtualización (VCF)`, sin ninguno de sus tres ancestros numerados, y el
    chunk 69 -- que es la sección 3.3 -- salió colgado de `· Equipo Principal de
    Almacenamiento de BackUp`, que pertenece a 3.2.

    La regla: si el pliego hubiera querido que ese título fuera hermano de las
    secciones numeradas, lo habría numerado. Entonces cada tramo de encabezados
    sin numerar se **desplaza en bloque** para quedar por debajo del último
    numerado. Se desplaza (no se aplasta) para no inventar hermandades entre
    ellos: lo que DI haya dicho sobre su jerarquía relativa se conserva tal cual.

    Sólo corre si el documento numera sus secciones -- en un pliego sin
    numeración (el de Rosario) no hay ningún encabezado numerado y la función no
    toca nada.
    """
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
            # Un anexo cierra el tramo pero NO puede ser piso de nada: su nivel
            # lo sigue poniendo DI, así que lo que venga después conserva el
            # piso del último encabezado numerado.
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


# --------------------------------------------------------------------------
# CHK-13: la tabla de contenidos no es contenido
# --------------------------------------------------------------------------
#
# En el PET de Bancor el índice del pliego se indexó como tres chunks (2.011,
# 94 y 290 caracteres) de la forma `col_1: 3.1.2. Virtualización / col_2: 12`.
# Uno de ellos dice literalmente `col_1: 5.3. Garantía y servicio post-venta`:
# una consulta sobre garantías lo recupera con buen score y no prueba nada,
# porque el índice NOMBRA las secciones sin CONTENERLAS. Compite con la
# evidencia real en las ocho categorías.
#
# La detección es estructural y deliberadamente conservadora: descartar
# contenido real sería mucho peor que conservar ruido, así que se exigen cinco
# condiciones a la vez. Un cronograma escalonado ("Etapa 1: 30 días, Etapa 2:
# 60...") cumple las tres primeras, y por eso existen las dos últimas.
_INDEX_MIN_ENTRIES = 5
_INDEX_MIN_NUMBERED_RATIO = 0.75
_INDEX_MIN_DISTINCT_TARGETS = 3
_INDEX_MIN_SECTION_PREFIX_RATIO = 0.6

_COL_PREFIX_RE = re.compile(r"^col_\d+:\s*", re.MULTILINE)
_TRAILING_NUMBER_RE = re.compile(r"(?:^|\s)(\d{1,3})\s*$")
_ONLY_NUMBER_RE = re.compile(r"^\d{1,3}$")
# "1. Generalidades", "3.1.2. Virtualización". El punto final es obligatorio:
# sin él, "1 Plataforma de software" (la columna Ítem de una planilla de
# cotización) también matchearía.
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
    # Los números apuntan hacia adelante y crecen: son páginas de ESTE documento
    # recorridas en orden, no cantidades ni plazos.
    if numeros != sorted(numeros):
        return False
    if max(numeros) <= pagina or max(numeros) > paginas_totales:
        return False
    # Y lo que numeran son secciones: "1.", "3.1.2.". Sin esto, cualquier lista
    # creciente de cantidades pasaría.
    return con_prefijo / len(entradas) >= _INDEX_MIN_SECTION_PREFIX_RATIO


def _drop_index_listings(blocks: list[dict]) -> list[dict]:
    """Saca del pipeline los bloques que son el índice del pliego (CHK-13)."""
    if not blocks:
        return blocks

    paginas_totales = max((_safe_page(b) for b in blocks), default=1)
    descartar: set[int] = set()

    # a) tablas completas -- se evalúa la tabla entera, no cada fila: el índice
    #    de Bancor se parte en dos chunks por tamaño y la segunda mitad, sola,
    #    tiene una sola fila.
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

    # b) corridas de párrafos consecutivos en la misma página -- el índice a
    #    veces sigue en la página siguiente sin forma de tabla.
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

    # CHK-10: nada se descarta en silencio.
    logger.info(
        "indice_del_pliego_descartado",
        bloques_descartados=len(descartar),
        bloques_totales=len(blocks),
        paginas=sorted({_safe_page(blocks[i]) for i in descartar}),
        muestra=[str(blocks[i].get("content", ""))[:60] for i in sorted(descartar)[:3]],
    )
    return [block for indice, block in enumerate(blocks) if indice not in descartar]


# --------------------------------------------------------------------------
# CHK-15: el membrete de página no es contenido
# --------------------------------------------------------------------------
#
# `_detect_repeated_heading_boilerplate` ya filtra el membrete cuando Document
# Intelligence lo marca como encabezado -- el caso del pliego de Rosario. En el
# PET de Bancor viene como PÁRRAFO de cuerpo, y su propio docstring dice que un
# párrafo repetido no entra en ese chequeo. Resultado: un chunk entero de 40
# caracteres que dice "BANCO DE LA PROVINCIA DE CÓRDOBA / BANCOR", y ese mismo
# texto encabezando los chunks de tabla como si fuera la frase que las
# introduce.
#
# El riesgo es descartar una cláusula real, así que se exige que sea corto Y que
# se repita en la mayoría de las páginas: una cláusula con contenido no cumple
# las dos cosas a la vez.
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

    membrete = {texto for texto, paginas_vistas in paginas_por_texto.items() if len(paginas_vistas) >= umbral}
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

    # CHK-10: nada se descarta en silencio.
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

    El pipeline lo produce como `{"table_id": "T1"}`, pero varios llamadores
    (y tests) lo pasan como string pelado. Asumir la forma de dict acá hacía
    reventar `_drop_index_listings` con `'str' object has no attribute 'get'`
    -- y en `create_chunks` ese error lo habría comido el `except Exception`
    ancho de CHK-10, convirtiendo un error de tipos en un documento sin tablas.
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
    
    # CHK-13: el índice del pliego se saca antes que nada. Nombra las secciones
    # sin contenerlas, así que como evidencia no sirve y como texto indexado
    # compite con los artículos reales.
    ordered = _drop_index_listings(ordered)

    # CHK-15: el membrete que viene como párrafo de cuerpo, que
    # `_detect_repeated_heading_boilerplate` no mira por diseño.
    ordered = _drop_repeated_page_furniture(ordered)

    # FIX CRÍTICO (2026-08-12): Fusionar headings partidos ANTES de procesar
    # Ejemplo: "ARTÍCULO 12: PLA" (página N) + "ZO DE ENTREGA" (página N+1)
    ordered = _merge_split_headings_across_pages(ordered)

    # FIX (auditoría 2026-08-13): encabezados que DI cortó al medio dejando la
    # cola al principio del párrafo siguiente, en la misma página. Va después
    # de la fusión entre páginas y antes de normalizar niveles, porque cambia
    # el TEXTO del encabezado y eso es lo que después se clasifica.
    ordered = _merge_truncated_headings_with_body(ordered)

    ordered = _normalize_numbered_heading_levels(ordered)
    # CHK-16: la numeración decimal declara la jerarquía; le gana a lo que DI
    # infirió del tamaño de la tipografía.
    ordered = _normalize_decimal_heading_levels(ordered)
    ordered = _promote_run_in_headings(ordered)
    # CHK-19: va al final, después de `_promote_run_in_headings`, porque ése
    # emite encabezados con nivel 2 fijo -- que es exactamente el nivel que se
    # lleva puesta la jerarquía numerada.
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
            # FIX (auditoría 2026-08-13, destapado al arreglar CHK-04): antes
            # sólo se marcaba el encabezado MÁS INTERNO. Sus ancestros quedaban
            # como "sin cuerpo propio" y `pop_to_level` fabricaba un bloque
            # puro-encabezado para cada uno. Mientras esos bloques no generaban
            # chunks el error era invisible; en cuanto empezaron a generarlos,
            # cada ancestro de la jerarquía metía un chunk de ruido con sólo su
            # título ("PLIEGO DE CONDICIONES PARTICULARES" suelto).
            #
            # Un ancestro NO está sin representar porque el párrafo cuelgue de
            # una subsección suya: su contenido son sus descendientes. Sólo se
            # pierde de verdad el encabezado del que no cuelga nada, ni directo
            # ni indirecto -- la portada de un anexo.
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
        return _introductory_tail(previous["content"])
    return None


# Cuánto contexto introductorio se le pega a una tabla. Una frase que presenta
# una tabla no pasa de un par de renglones; más que esto ya es el cuerpo del
# artículo anterior, que además ya tiene su propio chunk.
_TABLE_CONTEXT_MAX_CHARS = 300


def _introductory_tail(content: object) -> str | None:
    """La frase que introduce a la tabla: el ÚLTIMO párrafo del bloque previo.

    FIX (auditoría 2026-08-14, hallazgo CHK-14): esto devolvía
    `previous["content"]` entero. Pero para cuando corre, el bloque previo ya
    pasó por `_merge_intermediate_blocks` y es la fusión de todos los párrafos
    de su sección -- así que la tabla se llevaba pegada la sección completa.

    Medido en el PET de Bancor: el chunk 15 (953 caracteres) aparece **entero**
    otra vez al principio del chunk 16, que es su tabla. Lo mismo entre el 13 y
    el 14. El texto queda indexado dos veces, ocupa lugar dos veces en el
    presupuesto de contexto, y hace que dos chunks compitan entre sí en
    retrieval diciendo lo mismo.

    El último párrafo es además el correcto, no sólo el más corto: en el chunk
    15 es `"PLATAFORMA INTEGRADA Y GESTIÓN CENTRALIZADA DE NUBE PRIVADA:
    BROADCOM VMWARE CLOUD FOUNDATION 9.1 O SUPERIOR"` -- exactamente el
    encabezado de la tabla de licencias que sigue. Los 850 caracteres previos
    hablan de otra cosa.
    """
    texto = str(content or "").strip()
    if not texto:
        return None

    parrafos = [parte.strip() for parte in texto.split("\n\n") if parte.strip()]
    if not parrafos:
        return None

    cola = parrafos[-1]
    if len(cola) <= _TABLE_CONTEXT_MAX_CHARS:
        return cola

    # Un último párrafo largo: se conserva su final, que es lo que empalma con
    # la tabla, cortando en borde de oración y si no de palabra.
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
    
    FASE 3 RAG (2026-08-11): Ahora también consolida filas consecutivas de la
    misma tabla en un único chunk semántico. Esto permite que una búsqueda de
    "presupuesto oficial" recupere el contexto completo de la tabla en lugar
    de solo una fila.
    
    Párrafos: se fusionan si comparten heading_path y página.
    Tablas: se fusionan si comparten table_id (filas de la misma tabla), pero
            con límite de tamaño para evitar chunks gigantes.
    
    FIX (2026-08): Mantiene lista completa de blocks mergeados con sus para_id/bbox
    para trazabilidad precisa en highlighting.
    
    V4 (2026-08-11): Agregado límite de tamaño para tablas grandes. Si una tabla
    excede CHUNKING_MAX_TABLE_TOKENS, se divide en múltiples chunks manteniendo
    contexto de la tabla en cada uno.
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
            
            # FASE 3: Consolidar filas consecutivas de la misma tabla
            if merged:
                previous = merged[-1]
                previous_ref = previous.get("table_ref") or {}
                current_ref = block.get("table_ref") or {}
                
                # Mergear si es la misma tabla (mismo table_id)
                same_table = (
                    previous.get("block_type") == "table"
                    and previous_ref.get("table_id") is not None
                    and previous_ref.get("table_id") == current_ref.get("table_id")
                )
                
                if same_table:
                    # Inicializar merged_blocks si no existe
                    if "merged_blocks" not in previous:
                        original_content = previous["content"]
                        previous["merged_blocks"] = [{
                            "para_id": previous.get("para_id"),
                            "bbox": previous.get("bbox", []),
                            "content": original_content,
                        }]
                    
                    # Verificar límite de tamaño antes de mergear
                    # Aproximación: 1 token ≈ 4 caracteres
                    combined_content = f"{previous['content']}\n{block['content']}"
                    approx_tokens = len(combined_content) / 4
                    
                    if approx_tokens > max_table_tokens:
                        # Tabla excede límite - crear nuevo chunk
                        # Mantener metadata de tabla para contexto
                        block["table_context"] = previous.get("table_context", "")
                        block["merged_blocks"] = [{
                            "para_id": block.get("para_id"),
                            "bbox": block.get("bbox", []),
                            "content": block.get("content", ""),
                        }]
                        merged.append(block)
                        continue
                    
                    # Agregar fila actual (dentro del límite)
                    previous["merged_blocks"].append({
                        "para_id": block.get("para_id"),
                        "bbox": block.get("bbox", []),
                        "content": block.get("content", ""),
                    })
                    
                    # Concatenar contenido (filas de tabla)
                    previous["content"] = combined_content
                    
                    # Actualizar row_index al último (para metadata)
                    if "table_ref" in previous and "row_index" in current_ref:
                        previous["table_ref"]["row_index"] = current_ref["row_index"]
                    
                    continue  # No agregar block actual, ya está mergeado
            
            # Primera fila de tabla o tabla no consecutiva
            if "merged_blocks" not in block:
                block["merged_blocks"] = [{
                    "para_id": block.get("para_id"),
                    "bbox": block.get("bbox", []),
                    "content": block.get("content", ""),
                }]
            merged.append(block)
            continue

        if block.get("is_heading"):
            # Headings no tienen bbox (no son contenido a subrayar)
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
                # FIX: Agregar block actual a la lista de blocks mergeados
                if "merged_blocks" not in previous:
                    # Inicializar con el block original del previous (contenido antes de mergear)
                    original_content = previous["content"]
                    previous["merged_blocks"] = [{
                        "para_id": previous.get("para_id"),
                        "bbox": previous.get("bbox", []),
                        "content": original_content,
                    }]
                # Agregar el block actual
                previous["merged_blocks"].append({
                    "para_id": block.get("para_id"),
                    "bbox": block.get("bbox", []),
                    "content": block.get("content", ""),
                })
                # Actualizar contenido mergeado
                previous["content"] = f"{previous['content']}\n\n{block['content']}"
                continue

        # Block nuevo que no se puede mergear
        if "merged_blocks" not in block:
            block["merged_blocks"] = [{
                "para_id": block.get("para_id"),
                "bbox": block.get("bbox", []),
                "content": block.get("content", ""),
            }]
        merged.append(block)

    return merged


def _normalize_for_matching(text: str) -> str:
    """Normaliza texto para matching (lowercase, sin acentos, sin puntuación)"""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    # Remover puntuación, mantener espacios
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

    # Mayor cantidad de matches; a igualdad, el que aparece primero.
    return min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]


def _classify_by_heading(heading_path: list[str]) -> str | None:
    """Clasifica un chunk por su título de sección, de la hoja hacia la raíz.

    FIX (auditoría 2026-08-13, hallazgo CHK-06): antes se concatenaba TODO el
    `heading_path` en un solo string y se desempataba por la posición más
    temprana del patrón. Como los ancestros van primero en esa concatenación,
    el desempate favorecía estructuralmente al ancestro por sobre la sección
    real.

    Caso concreto: `["LICITACIÓN PÚBLICA Nº 5/2026", "GARANTÍAS"]`
      - `identificacion_procedimiento` matchea "licitacion" en la posición 0
      - `garantias` matchea "garantia" en la posición ~26
      - empate en cantidad de matches (1 y 1) -> ganaba el ancestro
    Toda la sección de garantías de ese pliego quedaba clasificada como
    identificación del procedimiento. Y como el título tiene prioridad absoluta
    sobre las keywords del contenido, nada aguas abajo podía corregirlo.

    Ahora se clasifica de la hoja hacia la raíz: el encabezado más específico
    decide, y los ancestros sólo se consultan si la hoja no matchea nada. Eso
    también hace que el desempate por posición opere DENTRO de un mismo
    encabezado, que es para lo que se escribió.
    """
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

    glossary_path = Path(__file__).resolve().parents[1] / "analysis" / "extraction" / "glossary.json"
    if not glossary_path.exists():
        return {}

    with glossary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _term_appears_in(normalized_term: str, content_tokens: set[str], padded_content: str) -> bool:
    """¿El término del glosario aparece en el chunk?

    FIX (auditoría 2026-08-13, hallazgo CHK-07): un término de varias palabras
    se descomponía en un CONJUNTO de tokens y matcheaba si todos aparecían en
    cualquier lugar del chunk, en cualquier orden y a cualquier distancia.

    `"mantenimiento de oferta"` se volvía `{mantenimiento, de, oferta}`. La
    palabra "de" está en el 100% de los chunks en castellano, así que en la
    práctica alcanzaba con que "mantenimiento" y "oferta" aparecieran sueltas.
    Un párrafo de servicios —*"el adjudicatario será responsable del
    mantenimiento preventivo de los equipos… La oferta económica deberá
    contemplar…"*— matcheaba como garantías. Dos o tres de estos falsos
    positivos sobre un chunk corto alcanzan para que CHK-08 lo declare
    `primary_category` de una categoría que no le corresponde.

    Ahora un término de varias palabras se busca como FRASE, con bordes de
    palabra. Es estrictamente más preciso y más barato que el subconjunto.
    """
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
    # Los espacios de los bordes permiten buscar una frase sin que matchee a
    # mitad de palabra ("oferta" dentro de "ofertante").
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


def _compute_density_score(match_count: int, content_length: int, category_weight: float = 1.0) -> float:
    """Calcula score normalizado por densidad de keywords en el contenido.
    
    Fórmula:
        term_coverage = min(match_count / SATURATION, 1.0)
        keyword_density = min(match_count / (content_length / 100), 1.0)
        score = term_coverage * keyword_density * category_weight
    
    Args:
        match_count: Cantidad de términos únicos del glossary que matchearon
        content_length: Cantidad de palabras en el chunk
        category_weight: Peso/boost de la categoría (default 1.0)
    
    Returns:
        Score normalizado entre 0.0 y 1.0

    CHK-08 (auditoría 2026-08-13), con el diagnóstico corregido el 2026-08-14.

    El hallazgo reportaba dos problemas. Al ir a arreglarlos, sólo uno era lo
    que decía:

    1. **El comentario decía lo contrario de lo que hace el código, y el
       equivocado era el comentario.** Decía "normalizado por cada 100 palabras
       para evitar penalizar chunks largos", pero
       `match_count / (content_length / 100)` es *inversamente* proporcional a
       la longitud. Ahora bien, eso es lo correcto: un término que aparece una
       vez en 700 palabras SÍ es menos indicativo que uno que aparece una vez
       en 100. Densidad significa exactamente eso. Se arregla el comentario, no
       la fórmula.

    2. **El piso `max(content_length / 100.0, 1.0)` no era la causa de la
       saturación: era un no-op.** Verificado por enumeración sobre
       `content_length` de 1 a 1500 y `match_count` de 1 a 20: no existe una
       sola combinación donde el piso cambie el resultado, porque para
       `content_length < 100` el cociente ya es ≥ 1 y el `min(..., 1.0)`
       posterior lo recorta igual.

       El efecto reportado sí es real —un chunk de menos de 100 palabras con UN
       solo match llega a `(1/4) * 1.0 = 0.25`, que es exactamente
       `_DEFAULT_PRIMARY_THRESHOLD`—, pero la causa es otra: el **punto de
       saturación** de la densidad está implícitamente en *1 match cada 100
       palabras*. Con esa unidad, cualquier chunk corto es máximamente denso por
       definición. Y las tablas de un pliego —cronogramas y planillas de
       cotización— son mayoritariamente chunks cortos.

    Corregir eso es mover la calibración, no arreglar un bug: cambia qué chunks
    pasan el umbral. Se necesita el set de chunks etiquetados para saber si
    mejora o empeora. Lo que sí se hace acá es **sacar la calibración de la
    penumbra**: el punto de saturación pasa a ser una constante con nombre
    (`_DENSITY_SATURATION_PER_100_WORDS`) en vez de estar escondido en la
    unidad de una división. El valor actual se conserva, así que el
    comportamiento no cambia: queda un solo lugar donde tocar cuando lleguen los
    datos.
    """
    if match_count == 0 or content_length == 0:
        return 0.0

    # Coverage: qué porcentaje del umbral de saturación alcanzamos
    term_coverage = min(match_count / _KEYWORD_SCORE_SATURATION, 1.0)

    # Density: cuántos matches por cada 100 palabras, medido contra el punto en
    # que se considera "máximamente denso".
    words_per_100 = max(content_length / 100.0, 1.0)
    matches_per_100_words = match_count / words_per_100
    keyword_density = min(matches_per_100_words / _DENSITY_SATURATION_PER_100_WORDS, 1.0)

    # Score combinado con peso de categoría
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
    """Clasifica un chunk en categorías usando scoring adaptativo por densidad.
    
    CAMBIO v2 (2026-08-12): Usa thresholds configurables por categoría en vez de
    magic numbers hardcodeados. Cada categoría define su propio umbral en glossary.json.

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
    chunk_id = chunk.get("chunk_id", "unknown")

    # 1. Clasificación por título
    heading_category = _classify_by_heading(heading_path)

    # 2. Clasificación por keywords (scoring de densidad)
    keyword_scores = _classify_by_keywords(content, glossary)

    # 3. Determinar categoría primary usando thresholds configurables
    primary_category = heading_category  # El título tiene prioridad

    # Si no hay título claro, usar keyword matching con threshold
    if not primary_category and keyword_scores:
        # Buscar categoría que supere su threshold de primary
        candidates = []
        for cat, score in keyword_scores.items():
            entry = glossary.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            primary_threshold = thresholds.get("primary", _DEFAULT_PRIMARY_THRESHOLD)
            
            if score >= primary_threshold:
                candidates.append((cat, score))
        
        if candidates:
            # Si hay múltiples candidatos, tomar el de mayor score
            primary_category = max(candidates, key=lambda x: x[1])[0]
            
            # Logging de ambigüedades: si hay múltiples candidatos con scores cercanos
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
    
    # FIX (auditoría 2026-08-13, hallazgo CHK-05): acá había un fallback que
    # asignaba "identificacion_procedimiento" a todo chunk que no se pudiera
    # clasificar, con el argumento de que era "la categoría menos específica".
    # El efecto real era convertirla en el tacho de basura de la clasificación:
    # considerandos, remisiones normativas y formalidades -- la mayoría del
    # texto de relleno de un pliego -- quedaban etiquetados como identificación
    # del procedimiento.
    #
    # Eso no es una etiqueta inocua. `_retrieve_with_category_priority` le da
    # +20% de boost a los chunks cuya `primary_category` coincide con la
    # categoría objetivo, así que al extraer la carátula TODO el ruido del
    # documento competía boosteado contra la carátula real.
    #
    # `None` es la respuesta correcta y no requiere ningún caso especial aguas
    # abajo: un chunk sin categoría simplemente no recibe boost (la comparación
    # `primary_category == category` es False), que es exactamente lo que se
    # quiere para un chunk que no se pudo clasificar. Sigue siendo recuperable
    # por BM25 y por similitud vectorial como cualquier otro.

    # 4. Categorías secundarias: todas las categorías que superen el threshold secundario
    secondary_categories = []
    for cat, score in keyword_scores.items():
        if cat == primary_category:
            continue  # No incluir la primary en secondary
        
        entry = glossary.get(cat, {})
        thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
        secondary_threshold = thresholds.get("secondary", _DEFAULT_SECONDARY_THRESHOLD)
        
        if score >= secondary_threshold:
            secondary_categories.append(cat)

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": keyword_scores,
    }


def _blocks_data_for(block: dict, texto: str, page_number: int) -> list[dict]:
    """Los bloques originales que efectivamente están en `texto`.

    FIX (auditoría 2026-08-13, hallazgo CHK-02): `_merge_intermediate_blocks`
    fusiona N párrafos en un bloque y guarda sus `merged_blocks` (para_id + bbox
    de cada uno). Después `_split_block_into_chunks` vuelve a partir ese bloque
    en M piezas -- y cada pieza recibía la lista COMPLETA de los N, sin filtrar
    cuáles de esos párrafos están realmente en ella.

    Una sección de 5 párrafos partida en 2 chunks daba un segundo chunk que
    declaraba como fuente los bbox de los 5. El `source` persistido en el índice
    miente: cualquier consumidor que no vuelva a filtrar por contenido obtiene la
    región equivocada.
    """
    merged_blocks = block.get("merged_blocks") or []
    if not merged_blocks:
        return [
            {
                "para_id": block.get("para_id"),
                "page": page_number,
                "bbox": block.get("bbox", []),
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

    # Si el filtro no deja ninguno -- puede pasar si el corte partió un párrafo
    # al medio -- se conservan todos antes que dejar la pieza sin trazabilidad.
    # Es el comportamiento viejo, pero acotado al caso en que no hay alternativa.
    if not incluidos:
        incluidos = merged_blocks

    return [
        {
            "para_id": mb.get("para_id"),
            "page": page_number,
            "bbox": mb.get("bbox", []),
            "content": mb.get("content", ""),
        }
        for mb in incluidos
    ]


# CHK-10: la diferencia entre "este bloque trae datos con una forma que no
# esperábamos" y "el código tiene un error". Los tres de acá son siempre lo
# segundo: no hay dato de un pliego que produzca un `NameError`. Atraparlos
# junto con el resto convertía cualquier bug del pipeline en un documento
# indexado al que le faltan pedazos, sin que nada aguas abajo lo note.
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
            
            # RAG ARCHITECTURE FIX (2026-08-11): Separar metadata de content.
            # 
            # ANTES: heading_prefix se inyectaba en content → duplicación innecesaria
            # AHORA: 
            #   - heading_path completo → metadata (section_path, title)
            #   - content → SOLO el párrafo/tabla puro
            #   - embedding → se genera con contexto (title + content) en embeddings.py
            #
            # Esto previene false positives en retrieval y permite highlighting preciso.
            section_path = " > ".join(heading_path) if heading_path else "general"
            title = heading_path[-1] if heading_path else None  # Último nivel = título de sección
            
            # Para embeddings: se usará title + content (ver embeddings.py)
            # Para storage: solo content puro

            if block_type == "table":
                row_content = str(block["content"])
                # Tablas: mantener table_context (párrafo introductorio) pero NO heading
                context_parts = [block.get("table_context"), row_content]
                full_content = "\n\n".join([p for p in context_parts if p])
                row_tokens = _tokenize(full_content)
                if not row_tokens:
                    continue

                # CHK-02: sólo los bloques que están en ESTA fila.
                blocks_data = _blocks_data_for(block, full_content, page_number)

                # RAG ARCHITECTURE: Campo source estructurado para highlighting
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
                    # PARENT/CHILD CHUNKING (US-3.1): las tablas no se subdividen
                    # en incisos -- siempre quedan como chunk "normal".
                    "chunk_type": "normal",
                }

                # Clasificar categorías del chunk
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
                continue

            if block.get("is_heading"):
                # FIX (auditoría 2026-08-13, hallazgo CHK-04): antes esto ponía
                # `body = ""` y más abajo `content_pieces = []`, así que el
                # bloque NO generaba ningún chunk -- pese a que el comentario
                # decía "crear chunk vacío con metadata" y a que
                # `_to_intermediate_blocks` fabrica estos bloques justamente
                # para "no perder" los encabezados sin cuerpo propio (ver toda
                # la maquinaria de `heading_has_body`). Era código muerto con
                # pérdida de información.
                #
                # Efecto concreto: la portada de un anexo -- "ANEXO III -
                # DECLARACIÓN JURADA DE APTITUD PARA CONTRATAR", un título solo,
                # con el formulario en la página siguiente bajo otro encabezado
                # -- simplemente NO EXISTÍA en el índice. La categoría
                # `anexos_obligatorios` no podía recuperarlo y el sistema
                # informaba que el pliego no lo pedía.
                #
                # Éste es el único caso donde el texto del encabezado va al
                # `content`: no hay cuerpo que lo represente, y sin contenido el
                # chunk no es recuperable ni por BM25 ni por el vector.
                heading_text = heading_path[-1] if heading_path else ""
                content_pieces = [heading_text] if heading_text else []
            else:
                # RAG: NO inyectar heading en content → será agregado solo para embedding
                body = str(block["content"]).strip()
                content_pieces = _split_block_into_chunks(body, chunk_size, overlap) if body else []

            for chunk_content in content_pieces:
                if not chunk_content.strip():
                    continue

                # CHK-02: sólo los bloques que están en ESTA pieza.
                blocks_data = _blocks_data_for(block, chunk_content, page_number)

                # RAG ARCHITECTURE: Campo source estructurado para highlighting
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

                # PARENT/CHILD CHUNKING (auditoría 2026-08-12, US-3.1): un
                # artículo largo con incisos mete todo el contexto jurídico en
                # un solo chunk -- el retrieval recupera el artículo entero
                # aunque el query apunte a un inciso puntual. Si el chunk
                # supera `_PARENT_CHILD_MIN_CHARS` y tiene una estructura de
                # incisos clara, se conserva completo como "parent" (no se
                # pierde contexto) y además se generan chunks "child" -- uno
                # por inciso, más chicos y precisos para que el retrieval
                # matchee directamente. Ver
                # `_bmad-output/parent-child-chunking-implementation.md`.
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
                        # FIX (auditoría 2026-08-13, hallazgo CHK-03): el spread
                        # `{**chunk_dict}` es una copia SUPERFICIAL, así que
                        # `source` y `blocks` quedaban siendo literalmente el
                        # mismo objeto en memoria que el del parent -- una
                        # mutación en cualquiera se propagaba a todos.
                        #
                        # Y el contenido de ese `source` es el del artículo
                        # COMPLETO. Todo el punto de parent/child es que el child
                        # sea más preciso: el retrieval matchea el inciso puntual
                        # y el resaltado debería marcar ESE inciso. Con el source
                        # heredado, citar el inciso b) resaltaba el artículo
                        # entero, incisos a) y c) incluidos -- media página de
                        # resaltado para un dato de una línea.
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
                        # Cada inciso puede hablar de algo distinto al resto del
                        # artículo (ej: un inciso de garantías dentro de un
                        # artículo de "documentación a presentar") -- reclasificar
                        # por su propio contenido en vez de heredar la del parent.
                        child_classification = classify_chunk_categories(child_dict)
                        child_dict["primary_category"] = child_classification["primary_category"]
                        child_dict["secondary_categories"] = child_classification["secondary_categories"]
                        child_chunk_dicts.append(child_dict)
                        child_indices.append(chunk_index)

                    chunk_dict["child_chunk_indices"] = child_indices
                    chunks.append(chunk_dict)
                    chunks.extend(child_chunk_dicts)
                    chunk_index += 1
                    continue

                # Clasificar categorías del chunk
                classification = classify_chunk_categories(chunk_dict)
                chunk_dict["primary_category"] = classification["primary_category"]
                chunk_dict["secondary_categories"] = classification["secondary_categories"]

                chunks.append(chunk_dict)
                chunk_index += 1
        except _PROGRAMMING_ERRORS:
            # CHK-10: estos NO son "un bloque con datos raros", son errores de
            # programación. Atraparlos convertía un bug en pérdida silenciosa de
            # datos. Ya pasó dos veces en esta auditoría: un `NameError` por una
            # variable mal escrita en la rama de tablas de `_blocks_data_for`
            # produjo un documento indexado con CERO chunks de tabla, y un
            # `AttributeError` por asumir que `table_ref` es un dict estuvo a un
            # paso de hacer lo mismo. En los dos casos el análisis terminó
            # "bien", con menos contenido. Que propaguen.
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

    # CHK-10: un warning por bloque se pierde entre el ruido, y el resultado es
    # un análisis INCOMPLETO que aguas abajo se ve idéntico a uno completo. El
    # conteo agregado, en nivel error, es lo único que hace visible la pérdida.
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
