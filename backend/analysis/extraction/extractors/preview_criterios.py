from __future__ import annotations

import re
import unicodedata

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.engine.normalization import _aggregate_status
from analysis.extraction.schemas import TipoCriterioPreview
from analysis.extraction.state import GraphState

# FIX (2026-09-03, pedido de reducir redundancia entre preview y categorias):
# de los 10 criterios de preview, 5 se solapaban con categorias que ya tienen
# su propio extractor completo (garantias, plazos_clave, requisitos_admisibilidad,
# riesgos) -- volver a preguntarselos al LLM con un query genérico diluido
# producía peor recall que la categoria dedicada Y corría el riesgo de que
# preview dijera algo distinto de lo que decía la categoria completa para el
# mismo hecho. Ahora esos 5 se PROYECTAN desde los resultados ya calculados
# de esas categorias (que corren antes en el mismo grafo de fase 1 -- ver
# `analysis/extraction/graph/nodes.py`), sin volver a llamar al LLM ni a
# retrieval. El LLM de esta categoria solo cubre lo que ninguna categoria
# extrae hoy: forma de pago, moneda, tipo de cambio, anticipo financiero y
# responsabilidad por costos logísticos.
_QUERY = (
    "Extraer condiciones comerciales rápidas de decisión que no estén "
    "cubiertas por otras categorías: forma de pago, moneda de cotización, "
    "tipo de cambio aplicable, anticipo financiero y responsabilidad por "
    "costos logísticos o de instalación del equipamiento."
)


def _not_found_item(tipo: str) -> dict:
    """Placeholder explícito para un criterio que se buscó y no se encontró
    evidencia suficiente -- a diferencia de simplemente omitir el tipo, que
    es indistinguible de un tipo que nunca se buscó (bug reportado
    2026-09-03: preview mostraba solo 4 de los 10 criterios porque los
    faltantes ni se generaban). `source_references=[]` ya es válido para el
    schema (ver fix en `schemas.py::ExtractedItem`) y `merge_node` lo
    conserva vía `_drop_items_without_sources(..., keep_not_found_without_sources=True)`."""
    return {
        "tipo": tipo,
        "valor": None,
        "metadata": {},
        "confidence": 0.0,
        "source_references": [],
        "extraction_status": "not_found",
    }


def _normalize(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.lower()


def _has_any(text: str | None, keywords: list[str]) -> bool:
    normalized = _normalize(text)
    return any(keyword in normalized for keyword in keywords)


def _has_pattern(text: str | None, patterns: tuple[re.Pattern[str], ...]) -> bool:
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in patterns)


def _project_item(source_item: dict, tipo: str, *, valor: str | None = None, source_references: list | None = None) -> dict:
    """Copia un item ya extraído (y ya verificado contra sus citas) de otra
    categoría al formato PreviewCriterioItem, sin volver a llamar al LLM ni
    a retrieval -- mismas fuentes, mismo texto, solo re-etiquetado bajo el
    tipo de preview correspondiente."""
    metadata = dict(source_item.get("metadata") or {})
    metadata["_proyectado_de_categoria"] = source_item.get("tipo")
    return {
        "tipo": tipo,
        "valor": valor if valor is not None else source_item.get("valor"),
        "metadata": metadata,
        "confidence": source_item.get("confidence", 0.5),
        "confidence_llm": source_item.get("confidence_llm"),
        "source_references": (
            source_references if source_references is not None else source_item.get("source_references", [])
        ),
        "extraction_status": source_item.get("extraction_status", "success"),
    }


_MERGE_MATCHES_MAX_ITEMS = 3


def _merge_matches(matches: list[dict], tipo: str) -> dict:
    """Combina varios items de la categoría fuente que matchean el mismo
    criterio de preview en uno solo (valor concatenado, fuentes unidas), en
    vez de perder información quedándose solo con el primero.

    FIX (2026-09-03, bug reportado: "requisitos_tecnicos_excluyentes" en un
    pliego real pegaba TODO un chorizo de información -- 12+ requisitos
    concatenados en un solo `valor` de cientos de caracteres). Esta función
    la usan `_project_requisitos_tecnicos` y `_project_multas_penalidades`,
    cuyas categorías fuente (`requisitos_admisibilidad`, `riesgos`) pueden
    tener muchos matches por keyword para un mismo pliego -- un pliego con
    varias certificaciones ISO/Partner obligatorias matcheaba 12+ items de
    requisitos_admisibilidad, y concatenar TODOS sin límite viola el propósito
    de esta categoría: preview es un vistazo rápido de decisión, no el detalle
    completo (que ya está en la categoría dedicada). Se limita a los
    `_MERGE_MATCHES_MAX_ITEMS` de mayor confidence, con una nota de cuántos
    quedaron afuera -- el dato completo sigue disponible en
    requisitos_admisibilidad/riesgos, esta categoría solo resume."""
    ordered = sorted(matches, key=lambda item: item.get("confidence", 0.0) or 0.0, reverse=True)
    kept = ordered[:_MERGE_MATCHES_MAX_ITEMS]
    omitted = len(ordered) - len(kept)

    valores = [m.get("valor") for m in kept if m.get("valor")]
    valor = "; ".join(dict.fromkeys(valores))
    if omitted > 0:
        valor = f"{valor} (+{omitted} más, ver detalle completo en la categoría correspondiente)"

    sources: list = []
    for match in kept:
        sources.extend(match.get("source_references") or [])
    best = max(kept, key=lambda item: item.get("confidence", 0.0) or 0.0)
    return _project_item(best, tipo, valor=valor, source_references=sources)


def _project_garantias_cauciones(garantias: list[dict]) -> list[dict]:
    if not garantias:
        return [_not_found_item("garantias_cauciones")]
    best = max(garantias, key=lambda item: item.get("confidence", 0.0) or 0.0)
    return [_project_item(best, "garantias_cauciones")]


# Heurística de texto libre: `referencia`/`texto_original` de PlazoItem no
# tienen taxonomía cerrada (ver docstring de PlazoItem en schemas.py), así
# que el match es por palabras clave. Puede no encontrar nada en pliegos con
# redacción muy distinta -- si no hay match, el criterio se emite igual como
# item "not_found" (no se inventa un valor, pero tampoco se omite el tipo).
_ENTREGA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bplazo\s+de\s+entrega\b"),
    re.compile(r"\bentrega\s+(?:del?|de\s+las?)\s+(?:equipamiento|bienes|servicios|insumos|mercaderia)s?\b"),
    re.compile(r"\bentrega\s+total\b"),
    re.compile(r"\b(?:plazo|termino)\s+de\s+provision\b"),
)
# FIX (2026-09-03, bug reportado: "Mantenimiento de oferta" en un pliego real
# quedaba como not_found en preview pese a estar bien extraído en
# plazos_clave): `las?` NO es "artículo opcional" -- es "la palabra 'la', con
# la 's' final opcional", así que el patrón viejo exigía literalmente la
# palabra "la"/"las" entre "de" y "oferta". Pliegos que titulan el ítem sin
# artículo ("Mantenimiento de oferta") o que solo lo mencionan con el verbo
# ("los oferentes deberán mantener sus propuestas por el plazo de...", que
# ademas usa "propuestas" en vez de "ofertas") no matcheaban con nada. Se
# amplía a: artículo opcional real (grupo `(?:la\s+|las\s+)?`, no `las?`),
# "propuesta(s)" como sinónimo de "oferta(s)", y la forma verbal "mantener
# (sus/su/la/las) oferta(s)/propuesta(s)". Sigue siendo una heurística de
# texto libre (no reemplaza una clasificación semántica real -- ver plan de
# fixes de RAG), así que puede seguir sin matchear redacciones muy distintas;
# si eso vuelve a pasar, la solución de fondo es la Fase 3.2 del plan
# (clasificación LLM sobre los ítems ya extraídos), no otro patrón más acá.
_MANTENIMIENTO_OFERTA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmantenimiento\s+de\s+(?:la\s+|las\s+)?ofertas?\b"),
    re.compile(r"\bmantenimiento\s+de\s+(?:la\s+|las\s+)?propuestas?\b"),
    re.compile(r"\bmantener\s+(?:sus\s+|su\s+|la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
    re.compile(r"\bvalidez\s+de\s+(?:la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
    re.compile(r"\bvigencia\s+de\s+(?:la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
)


def _project_plazos_clave(plazos: list[dict]) -> list[dict]:
    projected: list[dict] = []

    entrega_matches = [
        p for p in plazos
        if _has_pattern(
            f"{p.get('referencia', '')} {p.get('texto_original', '')}",
            _ENTREGA_PATTERNS,
        )
    ]
    if entrega_matches:
        item = _merge_matches(entrega_matches, "tiempo_entrega")
        item["valor"] = entrega_matches[0].get("texto_original") or item["valor"]
        projected.append(item)
    else:
        projected.append(_not_found_item("tiempo_entrega"))

    mantenimiento_matches = [
        p for p in plazos
        if _has_pattern(
            f"{p.get('referencia', '')} {p.get('texto_original', '')}",
            _MANTENIMIENTO_OFERTA_PATTERNS,
        )
    ]
    if mantenimiento_matches:
        item = _merge_matches(mantenimiento_matches, "mantenimiento_oferta")
        item["valor"] = mantenimiento_matches[0].get("texto_original") or item["valor"]
        projected.append(item)
    else:
        projected.append(_not_found_item("mantenimiento_oferta"))

    return projected


# Igual que arriba: heurística por palabras clave sobre el `valor` de
# RequisitoAdmisibilidadItem, filtrando primero a los obligatorios. No
# reemplaza un juicio experto -- puede dejar afuera requisitos técnicos con
# vocabulario que no matchea, o incluir alguno límite. Pensado para dar una
# señal rápida en preview, no como sustituto de la categoría completa
# (`requisitos_admisibilidad`), que sigue teniendo el detalle completo.
_TECNICO_EXCLUYENTE_KEYWORDS = [
    "iso", "certificacion", "certificado", "partner", "membresia",
    "vmware", "microsoft", "broadcom", "tecnico", "tecnica", "seguridad",
    "marca", "fabricante",
]


def _project_requisitos_tecnicos(requisitos: list[dict]) -> list[dict]:
    matches = [
        r for r in requisitos
        if (r.get("metadata") or {}).get("obligatorio") == "si"
        and _has_any(r.get("valor"), _TECNICO_EXCLUYENTE_KEYWORDS)
    ]
    if not matches:
        return [_not_found_item("requisitos_tecnicos_excluyentes")]
    return [_merge_matches(matches, "requisitos_tecnicos_excluyentes")]


# Riesgos financieros/operativos que mencionan multas o penalidades -- mismo
# tipo de heurística por palabras clave que las anteriores.
_MULTAS_KEYWORDS = ["multa", "penalidad", "penaliza"]


def _project_multas_penalidades(riesgos: list[dict]) -> list[dict]:
    matches = [r for r in riesgos if _has_any(r.get("valor"), _MULTAS_KEYWORDS)]
    if not matches:
        return [_not_found_item("multas_penalidades")]
    return [_merge_matches(matches, "multas_penalidades")]


_MONEDA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:usd|u\$s|ars|dolares?|dolares?\s+estadounidenses?)\b"),
    re.compile(r"\bmoneda\s+de\s+cotizacion\b"),
    re.compile(r"\bcotizar(?:se|an|a)?\s+en\s+"),
)
_TIPO_CAMBIO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btipo\s+de\s+cambio\b"),
    re.compile(r"\bcotizacion\s+del\s+dolar\b"),
)
_FORMA_PAGO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bforma\s+de\s+pago\b"),
    re.compile(r"\bcontra\s+entrega\b"),
    re.compile(r"\bpago\s+a\s+\d+"),
    re.compile(r"\bfactura(?:s)?\b"),
)
_ANTICIPO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\banticipo\b"),
    re.compile(r"\badelanto\s+financiero\b"),
)
_COSTOS_LOGISTICOS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcostos?\s+logisticos?\b"),
    re.compile(r"\btransporte\b"),
    re.compile(r"\bdesembalaje\b"),
    re.compile(r"\bflete\b"),
    re.compile(r"\bseguros?\b"),
    re.compile(r"\b(?:a\s+cargo\s+del\s+proveedor|por\s+cuenta\s+del\s+proveedor)\b"),
    re.compile(r"\bjaula\s+interior\b"),
)


def _item_text_with_citations(item: dict) -> str:
    parts = [str(item.get("valor") or "")]
    for ref in item.get("source_references") or []:
        parts.append(str(ref.get("citation") or ""))
    return " ".join(parts)


def _project_preview_llm_fields_from_riesgos(riesgos: list[dict]) -> list[dict]:
    """Fallback de preview para criterios comerciales/logísticos.

    Si la evidencia ya aparece en `riesgos`, se proyecta al criterio preview
    correspondiente para evitar depender únicamente de un llamado LLM diluido
    sobre 5 tipos en simultáneo.
    """
    if not riesgos:
        return [
            _not_found_item("forma_pago"),
            _not_found_item("moneda"),
            _not_found_item("tipo_cambio"),
            _not_found_item("anticipo_financiero"),
            _not_found_item("responsabilidad_costos_logisticos"),
        ]

    def _matches(patterns: tuple[re.Pattern[str], ...]) -> list[dict]:
        return [
            item
            for item in riesgos
            if _has_pattern(_item_text_with_citations(item), patterns)
        ]

    projections: list[dict] = []
    mapping: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
        ("forma_pago", _FORMA_PAGO_PATTERNS),
        ("moneda", _MONEDA_PATTERNS),
        ("tipo_cambio", _TIPO_CAMBIO_PATTERNS),
        ("anticipo_financiero", _ANTICIPO_PATTERNS),
        ("responsabilidad_costos_logisticos", _COSTOS_LOGISTICOS_PATTERNS),
    )

    for tipo, patterns in mapping:
        matches = _matches(patterns)
        if not matches:
            projections.append(_not_found_item(tipo))
            continue
        projections.append(_merge_matches(matches, tipo))

    return projections


def extractor_preview_criterios(state: GraphState) -> GraphState:
    delta = run_extractor(
        state=state,
        result_key="preview_criterios",
        state_field="preview_criterios",
        status_field="preview_criterios_status",
        prompt_file_name="preview_criterios.txt",
        query=_QUERY,
    )

    llm_items = list(delta.get("preview_criterios") or [])

    projected: list[dict] = []
    projected += _project_garantias_cauciones(state.get("garantias", []))
    projected += _project_plazos_clave(state.get("plazos", []))
    projected += _project_requisitos_tecnicos(state.get("requisitos_admisibilidad", []))
    projected += _project_multas_penalidades(state.get("riesgos", []))
    projected += _project_preview_llm_fields_from_riesgos(state.get("riesgos", []))

    combined = [*llm_items, *projected]

    # Red de seguridad genérica (2026-09-03): pase lo que pase con el LLM y
    # las proyecciones de arriba, los 10 tipos de `TipoCriterioPreview`
    # siempre terminan representados -- si el LLM no emitió item para un tipo
    # que le corresponde (a pesar de que el prompt ya le pide un item
    # "not_found" en vez de omitirlo), se completa acá. Evita que el
    # checklist de preview vuelva a mostrar menos de 10 criterios por un
    # incumplimiento puntual del LLM.
    tipos_presentes = {str(item.get("tipo")) for item in combined}
    for tipo in TipoCriterioPreview:
        if tipo.value not in tipos_presentes:
            combined.append(_not_found_item(tipo.value))

    delta["preview_criterios"] = combined
    # El status que devuelve run_extractor solo contempla los items del LLM
    # (5 de los 10 criterios) -- se recalcula acá con la lista completa,
    # incluyendo lo proyectado. merge_node lo puede seguir ajustando después
    # (ver `_drop_items_without_sources`/`_keep_schema_valid_items`), este es
    # solo el punto de partida.
    delta["preview_criterios_status"] = _aggregate_status(combined)

    return delta
