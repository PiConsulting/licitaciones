from __future__ import annotations

import re
import unicodedata
from typing import Any

import structlog

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.engine.normalization import _aggregate_status
from analysis.extraction.schemas import TipoCriterioPreview
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)

# 5 de los 10 criterios se PROYECTAN desde categorías ya extraídas (fase 1, no se re-preguntan al LLM); el LLM de esta categoría solo cubre lo que ninguna otra extrae.
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


# `tipo` es una instancia viva del enum en la misma corrida (no string); `str(enum)` da "Clase.X", no el value -- por esto las guardias de contenido no disparaban. Mismo bug espejado en synthesis.py::_tipo_value.
def _tipo_value(raw_tipo: Any) -> str:
    value = getattr(raw_tipo, "value", raw_tipo)
    return str(value or "").strip()


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


def _merge_matches(matches: list[dict], tipo: str, *, separator: str = "; ", max_items: int | None = None) -> dict:
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
    limit = max_items if max_items is not None else _MERGE_MATCHES_MAX_ITEMS
    kept = ordered[:limit]
    omitted = len(ordered) - len(kept)

    valores = [m.get("valor") for m in kept if m.get("valor")]
    valor = separator.join(dict.fromkeys(valores))
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


# Heurística de palabras clave sobre texto libre (PlazoItem no tiene taxonomía cerrada); sin match cae a "not_found".
# Incluye "ejecución"/"realización" de obra, no solo "entrega": pliegos de obra/servicios describen el mismo concepto sin la palabra "entrega" (bug real: Nucleoeléctrica).
_ENTREGA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bplazo\s+de\s+entrega\b"),
    re.compile(r"\bentrega\s+(?:del?|de\s+las?)\s+(?:equipamiento|bienes|servicios|insumos|mercaderia)s?\b"),
    re.compile(r"\bentrega\s+total\b"),
    re.compile(r"\b(?:plazo|termino)\s+de\s+provision\b"),
    re.compile(r"\b(?:plazo|termino)\s+de\s+ejecucion\b"),
    re.compile(r"\bejecucion\s+(?:completa\s+)?de\s+(?:la\s+obra|los\s+trabajos|el\s+contrato|la\s+prestacion)\b"),
    re.compile(r"\brealizacion\s+de\s+la\s+obra\b"),
)
# FIX 2026-09-03: `las?` exigía literalmente "la"/"las"; ahora cubre artículo opcional real, "propuesta(s)" como sinónimo, y la forma verbal "mantener oferta/propuesta". Heurística de texto libre, no clasificación semántica.
_MANTENIMIENTO_OFERTA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmantenimiento\s+de\s+(?:la\s+|las\s+)?ofertas?\b"),
    re.compile(r"\bmantenimiento\s+de\s+(?:la\s+|las\s+)?propuestas?\b"),
    re.compile(r"\bmantener\s+(?:sus\s+|su\s+|la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
    re.compile(r"\bvalidez\s+de\s+(?:la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
    re.compile(r"\bvigencia\s+de\s+(?:la\s+|las\s+)?(?:ofertas?|propuestas?)\b"),
)


# FIX 2026-09-16 (Santa Fe, multi-documento): tomar el primer match perdía el que tenía cifra real cuando el pliego marco solo nombraba el concepto sin número; ahora se prefiere el match con duración concreta.
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


# Camino primario: filtra por el tag que el LLM ya asigna (más confiable que adivinar por vocabulario).
_TECNICO_EXCLUYENTE_TIPOS = {"certificacion", "requisito_tecnico_excluyente"}

# Fallback por keywords solo si ningún ítem viene etiquetado (pliego pre-cambio); señal rápida, no sustituye la categoría completa.
_TECNICO_EXCLUYENTE_KEYWORDS = [
    "iso", "certificacion", "certificado", "partner", "membresia",
    "vmware", "microsoft", "broadcom", "tecnico", "tecnica", "seguridad",
    "marca", "fabricante",
]


_REQUISITOS_TECNICOS_MAX_ITEMS = 8


def _project_requisitos_tecnicos(requisitos: list[dict]) -> list[dict]:
    tagged = [r for r in requisitos if _tipo_value(r.get("tipo")) in _TECNICO_EXCLUYENTE_TIPOS]
    matches = tagged or [
        r for r in requisitos
        if (r.get("metadata") or {}).get("obligatorio") == "si"
        and _has_any(r.get("valor"), _TECNICO_EXCLUYENTE_KEYWORDS)
    ]
    if not matches:
        return [_not_found_item("requisitos_tecnicos_excluyentes")]
    # Separador "\n" (no "; "): el frontend renderiza `valor` multilínea como lista de items.
    return [_merge_matches(matches, "requisitos_tecnicos_excluyentes", separator="\n", max_items=_REQUISITOS_TECNICOS_MAX_ITEMS)]


# Guardia determinística (bug real: Bancor mostraba "llave en mano" como responsabilidad de costos): si el valor es solo la modalidad de contratación, buscar en las citas una frase que sí diga quién paga.
_MODALIDAD_MENTION_RE = re.compile(
    r"llave\s+en\s+mano|provisi[oó]n\s+(?:e\s+instalaci[oó]n\s+)?integral",
    re.IGNORECASE,
)
_COSTO_RESPONSABLE_SNIPPET_RE = re.compile(
    r"(?:a\s+cargo\s+(?:del|de\s+la)|por\s+cuenta\s+(?:del|de\s+la))\s+"
    r"(?:proveedor|oferente|adjudicatario|contratista)[^.;\n]{0,80}"
    r"|(?:el|la)\s+(?:proveedor|oferente|adjudicatario|contratista)\s+"
    r"(?:asumir[aá]|asume|deber[aá]\s+asumir|correr[aá]\s+con)[^.;\n]{0,80}",
    re.IGNORECASE,
)


# Guardia de contenido (Santa Fe): `moneda` debe nombrar una moneda concreta o cae a not_found; NO acepta "moneda nacional/extranjera" (frases genéricas de cláusulas de ajuste cambiario, no un nombre real).
_MONEDA_NOMBRE_RE = re.compile(
    r"\b(?:pesos?(?:\s+argentinos?)?|d[oó]lares?(?:\s+estadounidenses?)?|usd|u\$s|ars)\b",
    re.IGNORECASE,
)


def _has_currency_name(valor: str | None) -> bool:
    return bool(valor) and bool(_MONEDA_NOMBRE_RE.search(str(valor)))


def _currency_name_snippet(item: dict) -> str | None:
    for ref in item.get("source_references") or []:
        text = str(ref.get("citation_llm") or ref.get("citation") or "")
        match = _MONEDA_NOMBRE_RE.search(text)
        if match:
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            return text[start:end].strip()
    return None


def _is_modalidad_only(valor: str | None) -> bool:
    """True si el valor menciona la MODALIDAD de contratación (llave en mano/
    provisión integral) pero no aporta ya, en el mismo texto, quién asume los
    costos puntuales -- señal de que el valor describe el ALCANCE general, no
    la responsabilidad de costos que pide este criterio de preview."""
    if not valor:
        return False
    text = str(valor)
    return bool(_MODALIDAD_MENTION_RE.search(text)) and not bool(
        _COSTO_RESPONSABLE_SNIPPET_RE.search(text)
    )


def _cost_responsibility_snippet(item: dict) -> str | None:
    for ref in item.get("source_references") or []:
        text = str(ref.get("citation_llm") or ref.get("citation") or "")
        match = _COSTO_RESPONSABLE_SNIPPET_RE.search(text)
        if match:
            return match.group(0).strip()
    return None


def _apply_content_guards(items: list[dict]) -> list[dict]:
    """Guardias de contenido determinísticas para `forma_pago`/`moneda`/
    `responsabilidad_costos_logisticos`, aplicadas al resultado final sin
    importar si el item vino de la extracción directa de `preview_criterios.txt`
    o del fallback de `riesgos` -- ambas fuentes pueden, de forma no
    determinística, devolver un `valor` que describe la MODALIDAD de
    contratación en vez de responder la pregunta puntual del criterio."""
    result = []
    for item in items:
        tipo = _tipo_value(item.get("tipo"))
        if tipo == "responsabilidad_costos_logisticos" and _is_modalidad_only(item.get("valor")):
            snippet = _cost_responsibility_snippet(item)
            if snippet:
                item = dict(item)
                item["valor"] = snippet
            else:
                item = _not_found_item(tipo)
        elif tipo == "moneda" and item.get("valor") and not _has_currency_name(item.get("valor")):
            snippet = _currency_name_snippet(item)
            if snippet:
                item = dict(item)
                item["valor"] = snippet
            else:
                item = _not_found_item(tipo)
        result.append(item)
    return result


def extractor_preview_criterios(state: GraphState) -> GraphState:
    delta = run_extractor(
        state=state,
        result_key="preview_criterios",
        state_field="preview_criterios",
        status_field="preview_criterios_status",
        prompt_file_name="preview_criterios.txt",
        query=_QUERY,
    )

    # 6 campos ahora se extraen directo del prompt, no se proyectan desde `riesgos`: la doble fuente causaba una carrera no determinística por dedup (causa real de textos de otra categoría en estas cards).
    llm_items = list(delta.get("preview_criterios") or [])

    projected: list[dict] = []
    projected += _project_garantias_cauciones(state.get("garantias", []))
    projected += _project_plazos_clave(state.get("plazos", []))
    projected += _project_requisitos_tecnicos(state.get("requisitos_admisibilidad", []))

    combined = _apply_content_guards([*llm_items, *projected])

    # Red de seguridad: garantiza que los 10 tipos de TipoCriterioPreview siempre estén representados, aunque el LLM omita alguno.
    tipos_presentes = {_tipo_value(item.get("tipo")) for item in combined}
    for tipo in TipoCriterioPreview:
        if tipo.value not in tipos_presentes:
            combined.append(_not_found_item(tipo.value))

    delta["preview_criterios"] = combined
    # run_extractor solo contempla los items del LLM; se recalcula con la lista completa (incluye lo proyectado).
    delta["preview_criterios_status"] = _aggregate_status(combined)

    return delta
