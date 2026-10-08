"""Deteccion de indices/tablas de contenido y membretes de pagina repetidos, para descartarlos del chunking."""
from __future__ import annotations

import re
from collections import defaultdict

import structlog

logger = structlog.get_logger(__name__)

_INDEX_MIN_ENTRIES = 5
_INDEX_MIN_NUMBERED_RATIO = 0.75
_INDEX_MIN_DISTINCT_TARGETS = 3
_INDEX_MIN_SECTION_PREFIX_RATIO = 0.6
_COL_PREFIX_RE = re.compile(r"^col_\d+:\s*", re.MULTILINE)
_TRAILING_NUMBER_RE = re.compile(r"(?:^|\s)(\d{1,3})\s*$")
_ONLY_NUMBER_RE = re.compile(r"^\d{1,3}$")
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\.\s")
_PAGE_FURNITURE_MAX_CHARS = 120
_PAGE_FURNITURE_MIN_PAGES = 3
_PAGE_FURNITURE_MIN_PAGE_FRACTION = 0.6

# Contador de pagina ("Hoja 5 de 22"); cambia en cada pagina, por eso no lo
# agarra `_drop_repeated_page_furniture` (que descarta por texto EXACTO repetido).
# DI lo marca inconsistentemente: a veces cae como parrafo de cuerpo normal
# (caso real: Nucleoelectrica, "HOJA\n1 de 22").
_PAGE_COUNTER_RE = re.compile(
    r"^(?:hoja|p[aá]gina|pag\.?|page)\s*n?[º°]?\s*\d+\s*(?:de|/)\s*\d+\s*$",
    re.IGNORECASE,
)

# Mismo caso que el contador de pagina, pero para el sello de version/revision
# ("V 1.13") cuando DI lo deja como parrafo en vez de heading (headings.py ya
# cubre el caso heading). Caso real: PLIEGO_5443-26 sobrevivia como chunk huérfano.
_VERSION_STAMP_RE = re.compile(
    r"^(?:v|ver|vers(?:i[oó]n)?|rev(?:isi[oó]n)?)\.?\s*\d+(?:\.\d+)*\s*$",
    re.IGNORECASE,
)


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

    # Import diferido: block_merging importa de este módulo a nivel de módulo,
    # importar acá arriba crearía un ciclo.
    from indexing.chunking.block_merging import _table_group_key

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


def _drop_page_counters(blocks: list[dict]) -> list[dict]:
    """Saca los parrafos que son SOLO un contador de pagina ("Hoja 5 de 22",
    "Pagina 3/10") o un sello de version/revision ("V 1.13") -- ver
    `_PAGE_COUNTER_RE`/`_VERSION_STAMP_RE`. A diferencia de
    `_drop_repeated_page_furniture`, no depende de que el texto se repita
    exacto (el numero cambia en cada pagina/version), así que alcanza con que
    UN bloque matchee el patron."""
    descartar: set[int] = set()
    for indice, block in enumerate(blocks):
        if block.get("heading_level") is not None or block.get("table_ref"):
            continue
        texto = " ".join(str(block.get("content", "") or "").split())
        if texto and (_PAGE_COUNTER_RE.match(texto) or _VERSION_STAMP_RE.match(texto)):
            descartar.add(indice)

    if not descartar:
        return blocks

    logger.info(
        "contador_de_pagina_descartado",
        bloques_descartados=len(descartar),
        muestra=[str(blocks[i].get("content", ""))[:40] for i in sorted(descartar)[:5]],
    )
    return [block for indice, block in enumerate(blocks) if indice not in descartar]


def _safe_page(block: dict) -> int:
    try:
        return int(block.get("page_number") or 1)
    except (TypeError, ValueError):
        return 1
