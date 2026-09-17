from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import structlog

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.engine.llm_client import _call_llm
from analysis.extraction.engine.normalization import _aggregate_status
from analysis.extraction.schemas import TipoCriterioPreview
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)

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


# FIX (2026-09-16, bug reportado: preview mostraba "Plazo de mantenimiento de
# las ofertas." sin ningún número, mientras plazos_clave SÍ tenía "Plazo de
# Mantenimiento de la Oferta: 30 días corridos..." -- caso real: santa_fe,
# análisis multi-documento donde el pliego MARCO solo nombra el concepto
# ("Plazo de mantenimiento de las ofertas.") y el pliego PARTICULAR trae el
# número real. `mantenimiento_matches[0]`/`entrega_matches[0]` tomaba el
# primer match en el orden en que aparece en `plazos` -- que no tiene por qué
# ser el más completo. El fix es genérico (no depende de qué pliego/documento
# sea "el marco"): entre los matches, preferir el/los que tengan una duración
# concreta (un número + día/mes/año, o `expresion_relativa` ya estructurada)
# sobre uno que solo menciona el concepto sin cifra.
_DURATION_PATTERN = re.compile(r"\d+\s*\(?[a-z]*\)?\s*(?:dias?|meses|mes|anos?|horas?)\b")


def _has_concrete_duration(item: dict) -> bool:
    """`expresion_relativa` puede estar seteada con solo una referencia al
    concepto ("dentro del plazo de mantenimiento de la oferta", sin decir
    cuánto es) -- eso NO cuenta como duración concreta por sí solo. Se busca
    el patrón numérico en `expresion_relativa` + `texto_original` juntos."""
    combined = f"{item.get('expresion_relativa') or ''} {item.get('texto_original') or ''}"
    return bool(_DURATION_PATTERN.search(_normalize(combined)))


def _best_descriptive_match(matches: list[dict], patterns: tuple[re.Pattern[str], ...]) -> dict:
    """Entre varios ítems que matchean el mismo criterio de preview (por
    mencionarlo en `referencia` O en `texto_original`), elige el mejor para
    usar como `valor` legible, en este orden de preferencia:

    1. Ítems cuya propia `referencia` ya es sobre el tema (no solo una
       mención de paso dentro de un ítem que trata otra cosa) Y que además
       tienen una duración concreta.
    2. Cualquier ítem con duración concreta (aunque el tema central del ítem
       sea otro).
    3. El de mayor `confidence_llm` entre todos, si ninguno tiene duración.

    Caso real (santa_fe): "Devolución garantía de oferta" MENCIONA
    "mantenimiento de la oferta" de paso (para explicar cuándo se libera la
    garantía) y hasta tiene un número (30 días) -- pero ESE número es sobre
    la devolución, no sobre cuánto dura el mantenimiento. Su `referencia` no
    habla de "mantenimiento de oferta"; la del ítem correcto ("Mantenimiento
    de oferta") sí. Filtrar por `referencia` antes de mirar duración evita
    agarrar el número equivocado."""

    def es_sobre_el_tema(item: dict) -> bool:
        return _has_pattern(item.get("referencia", ""), patterns)

    on_topic = [m for m in matches if es_sobre_el_tema(m)]
    on_topic_with_duration = [m for m in on_topic if _has_concrete_duration(m)]

    if on_topic_with_duration:
        pool = on_topic_with_duration
    else:
        with_duration = [m for m in matches if _has_concrete_duration(m)]
        pool = with_duration or on_topic or matches

    return max(pool, key=lambda item: item.get("confidence_llm") or item.get("confidence") or 0.0)


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
        item["valor"] = (
            _best_descriptive_match(entrega_matches, _ENTREGA_PATTERNS).get("texto_original")
            or item["valor"]
        )
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
        item["valor"] = (
            _best_descriptive_match(mantenimiento_matches, _MANTENIMIENTO_OFERTA_PATTERNS).get(
                "texto_original"
            )
            or item["valor"]
        )
        projected.append(item)
    else:
        projected.append(_not_found_item("mantenimiento_oferta"))

    return projected


# Camino primario: el extractor de `requisitos_admisibilidad` ahora auto-etiqueta
# los ítems con `tipo` = `certificacion` / `requisito_tecnico_excluyente` (ver
# schemas.py::TipoRequisito y el prompt). Se filtra por ese tag, que es un juicio
# del LLM sobre el fragmento real -- más confiable que adivinar por vocabulario.
_TECNICO_EXCLUYENTE_TIPOS = {"certificacion", "requisito_tecnico_excluyente"}

# Fallback por palabras clave sobre el `valor`, solo si no hay ningún ítem
# etiquetado (pliego analizado antes de este cambio, o el LLM no taggeó). No
# reemplaza un juicio experto -- puede dejar afuera requisitos técnicos con
# vocabulario que no matchea (ej. "compatibilidad GNU/Linux"), o incluir alguno
# límite. Pensado para dar una señal rápida en preview, no como sustituto de la
# categoría completa (`requisitos_admisibilidad`), que tiene el detalle completo.
_TECNICO_EXCLUYENTE_KEYWORDS = [
    "iso", "certificacion", "certificado", "partner", "membresia",
    "vmware", "microsoft", "broadcom", "tecnico", "tecnica", "seguridad",
    "marca", "fabricante",
]


def _project_requisitos_tecnicos(requisitos: list[dict]) -> list[dict]:
    tagged = [r for r in requisitos if str(r.get("tipo") or "") in _TECNICO_EXCLUYENTE_TIPOS]
    matches = tagged or [
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

_PREVIEW_RIESGO_TYPES: tuple[str, ...] = (
    "forma_pago",
    "moneda",
    "tipo_cambio",
    "anticipo_financiero",
    "responsabilidad_costos_logisticos",
)


def _item_text_with_citations(item: dict) -> str:
    parts = [str(item.get("valor") or "")]
    for ref in item.get("source_references") or []:
        parts.append(str(ref.get("citation") or ""))
    return " ".join(parts)


def _regex_matches_for_preview_types(riesgos: list[dict]) -> dict[str, list[dict]]:
    if not riesgos:
        return {tipo: [] for tipo in _PREVIEW_RIESGO_TYPES}

    def _matches(patterns: tuple[re.Pattern[str], ...]) -> list[dict]:
        return [
            item
            for item in riesgos
            if _has_pattern(_item_text_with_citations(item), patterns)
        ]

    mapping: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
        ("forma_pago", _FORMA_PAGO_PATTERNS),
        ("moneda", _MONEDA_PATTERNS),
        ("tipo_cambio", _TIPO_CAMBIO_PATTERNS),
        ("anticipo_financiero", _ANTICIPO_PATTERNS),
        ("responsabilidad_costos_logisticos", _COSTOS_LOGISTICOS_PATTERNS),
    )
    return {tipo: _matches(patterns) for tipo, patterns in mapping}


def _normalize_preview_type_label(label: str) -> str | None:
    normalized = _normalize(label).replace("-", "_").replace(" ", "_")
    aliases = {
        "forma_pago": "forma_pago",
        "moneda": "moneda",
        "tipo_cambio": "tipo_cambio",
        "anticipo": "anticipo_financiero",
        "anticipo_financiero": "anticipo_financiero",
        "costos_logisticos": "responsabilidad_costos_logisticos",
        "responsabilidad_costos_logisticos": "responsabilidad_costos_logisticos",
    }
    return aliases.get(normalized)


def _dedupe_matches(items: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        citation_text = " ".join(
            str(ref.get("citation") or "") for ref in item.get("source_references") or []
        )
        signature = (str(item.get("valor") or ""), citation_text)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(item)
    return unique


def _classify_preview_fields_via_llm(
    riesgos: list[dict], *, correlation_id: str
) -> dict[str, list[dict]] | None:
    if not riesgos:
        return {tipo: [] for tipo in _PREVIEW_RIESGO_TYPES}

    payload = [
        {
            "index": idx,
            "texto": _item_text_with_citations(item)[:1800],
        }
        for idx, item in enumerate(riesgos)
    ]

    messages = [
        (
            "system",
            "Clasificas evidencias de riesgos en etiquetas de preview_criterios. "
            "Devuelve solo JSON válido con key 'classifications'.",
        ),
        (
            "human",
            (
                "Para cada item, devuelve una lista multi-etiqueta en 'tipos' usando "
                "solo: forma_pago, moneda, tipo_cambio, anticipo_financiero, "
                "responsabilidad_costos_logisticos. Si no aplica, devuelve lista vacía. "
                "Formato: {'classifications':[{'index':0,'tipos':['moneda']}, ...]}. "
                f"Items: {json.dumps(payload, ensure_ascii=False)}"
            ),
        ),
    ]

    try:
        parsed, _usage = _call_llm(messages, correlation_id=f"{correlation_id}-preview-projection")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "preview_projection_llm_failed_fallback_to_regex",
            correlation_id=correlation_id,
            error=str(exc)[:200],
            candidates=len(riesgos),
        )
        return None

    matches: dict[str, list[dict]] = {tipo: [] for tipo in _PREVIEW_RIESGO_TYPES}
    rows = parsed.get("classifications") or []
    if not isinstance(rows, list):
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_index = row.get("index")
        if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= len(riesgos):
            continue
        tipos = row.get("tipos") or []
        if not isinstance(tipos, list):
            continue
        for raw_tipo in tipos:
            if not isinstance(raw_tipo, str):
                continue
            normalized_tipo = _normalize_preview_type_label(raw_tipo)
            if normalized_tipo is None:
                continue
            matches[normalized_tipo].append(riesgos[raw_index])

    logger.info(
        "preview_projection_llm_applied",
        correlation_id=correlation_id,
        candidates=len(riesgos),
        matched_types=sum(1 for tipo in _PREVIEW_RIESGO_TYPES if matches[tipo]),
    )
    return matches


def _project_preview_llm_fields_from_riesgos(
    riesgos: list[dict], *, correlation_id: str | None = None
) -> list[dict]:
    """Fallback de preview para criterios comerciales/logísticos.

    Si la evidencia ya aparece en `riesgos`, se proyecta al criterio preview
    correspondiente para evitar depender únicamente de un llamado LLM diluido
    sobre 5 tipos en simultáneo.
    """
    regex_matches = _regex_matches_for_preview_types(riesgos)
    llm_matches = _classify_preview_fields_via_llm(
        riesgos,
        correlation_id=correlation_id or "preview_criterios",
    )

    projections: list[dict] = []
    for tipo in _PREVIEW_RIESGO_TYPES:
        merged = list(regex_matches[tipo])
        if llm_matches is not None:
            merged.extend(llm_matches.get(tipo, []))
        merged = _dedupe_matches(merged)

        if not merged:
            item = _not_found_item(tipo)
        else:
            item = _merge_matches(merged, tipo)

        metadata = dict(item.get("metadata") or {})
        metadata["_projection_source"] = (
            "llm_union_regex" if llm_matches is not None else "regex_fallback"
        )
        item["metadata"] = metadata
        projections.append(item)

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
    projected += _project_preview_llm_fields_from_riesgos(
        state.get("riesgos", []),
        correlation_id=str(state.get("correlation_id", "preview_criterios")),
    )

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
