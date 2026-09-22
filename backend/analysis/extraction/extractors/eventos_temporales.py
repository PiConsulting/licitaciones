from __future__ import annotations

import difflib
import json
import unicodedata

import structlog

from analysis.extraction.engine.base import run_extractor
from analysis.extraction.engine.llm_client import _call_llm
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)

_QUERY = (
    "Eventos, hitos y plazos temporales del proceso de licitación: fechas "
    "explícitas (recepción del pliego, apertura, adjudicación, firma de "
    "contrato, entregas) y plazos contados desde esos eventos ('X días "
    "corridos/hábiles desde...', 'dentro de los X días de...'). Tanto "
    "hitos con fecha propia como plazos que dependen de otro evento."
)


def _normalize(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.lower()


def _referenced_as_trigger(nombre: str | None, items: list[dict]) -> bool:
    return any(other.get("evento_disparador") == nombre for other in items)


# Reemplaza ~6 regex de post-filtrado que no generalizaban (releer memoria
# `eventos-temporales-auditoria-completa-2026-09-21`): el LLM ahora autodeclara 3 ejes
# semánticos (accion_concreta/es_ocurrencia_unica/depende_de_decision_discrecional) por ítem.
def _fails_structural_relevance(item: dict) -> bool:
    accion = str(item.get("accion_concreta") or "").strip()
    if len(accion) < 8:
        return True
    if item.get("es_ocurrencia_unica") is False:
        return True
    if item.get("depende_de_decision_discrecional") is True:
        return True
    return False


def _is_irrelevant_hito(item: dict, items: list[dict]) -> bool:
    """`_fails_structural_relevance` protegido por las mismas 2 excepciones
    que ya regían cada una de las funciones que reemplaza: una
    `fecha_explicita` propia es la señal más fuerte de que es un hito real,
    sin importar cómo se hayan declarado los 3 campos nuevos; y un ítem que
    otro usa como `evento_disparador` no se puede eliminar sin romper esa
    cadena de cálculo (regla 2 del prompt)."""
    if item.get("fecha_explicita"):
        return False
    if _referenced_as_trigger(item.get("nombre"), items):
        return False
    return _fails_structural_relevance(item)


def _is_orphan_non_self_mentioned(item: dict, items: list[dict]) -> bool:
    """`mencion_propia: False` (regla 2 del prompt) marca un ítem que el LLM
    creó SOLO para completar el `evento_disparador` de otro hito -- el pliego
    nunca lo menciona por sí mismo. Encontrado en Dell: "Cronograma del
    Proceso" salió con `mencion_propia: false` pero NADA lo usa como
    disparador -- ni cumplió el propósito para el que existe ese campo, ni es
    un hito real (es una referencia a un documento externo -- "las consultas
    se harán según el cronograma previsto", no una acción con fecha propia).
    Señal genérica: si el propio LLM ya dijo "esto no lo menciona el pliego
    por sí solo" y además nada depende de él, no aporta nada."""
    if item.get("mencion_propia") is not False:
        return False
    return not _referenced_as_trigger(item.get("nombre"), items)


def _strip_dangling_disparador(item: dict) -> dict:
    """Regla nueva del prompt: `evento_disparador` y `cantidad` van juntos o
    ninguno de los dos. Encontrado en 3 pliegos distintos (Dell, Ce.Si.Da,
    Nucleoeléctrica): el LLM a veces arma un `evento_disparador` a partir de
    una secuencia narrativa ("X luego de Y") que nunca da una cantidad de
    tiempo real, dejando `cantidad: null` -- río abajo, `timeline/materializer.py`
    convierte ese `null` en una duración de 0 (`int(cantidad or 0)`), mostrando
    un plazo "0 días corridos" que el pliego nunca afirmó. Se resuelve en
    código, no solo en el prompt (mismo patrón ya visto varias veces esta
    sesión: una instrucción de prompt no garantiza que el LLM la siga siempre
    en un map-reduce de docenas de fragmentos) -- si falta la cantidad, se
    quita toda la estructura de plazo relativo y el hito queda como ítem
    independiente, sin inventar una relación que el texto no cuantificó."""
    if item.get("evento_disparador") and item.get("cantidad") is None:
        item = dict(item)
        item["evento_disparador"] = None
        item["unidad"] = None
        item["tipo_dias"] = None
        item["direccion"] = None
        item["es_plazo_maximo"] = False
    return item


# NO CONECTADA a `_filter_non_hitos` (ver nota grande ahí): fuzzy matching de texto
# probado INSEGURO contra los 10 pliegos reales (fusiona pares que solo comparten
# vocabulario) -- queda documentada para retomar con un diseño distinto (síntesis LLM).
_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "en", "y", "o", "u", "a", "al",
    "un", "una", "unos", "unas", "para", "por", "con", "su", "sus", "que",
    "cada", "se", "es",
}
_MIN_TOKEN_LEN = 3
_TOKEN_OVERLAP_THRESHOLD = 0.75
_FUZZY_MATCH_THRESHOLD = 0.82


def _significant_tokens(normalized: str) -> set[str]:
    return {
        token
        for token in normalized.split(" ")
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


def _token_overlap_ratio(a_tokens: set[str], b_tokens: set[str]) -> float:
    """Ver docstring del mismo algoritmo en `timeline/materializer.py` (no se
    importa de ahí para no acoplar el módulo de extracción al de timeline --
    la lógica es chica, estable y ya está probada en ese otro contexto)."""
    if not a_tokens or not b_tokens:
        return 0.0
    smaller, larger = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    overlap = smaller & larger
    if not overlap:
        return 0.0
    if len(smaller) == 1:
        token = next(iter(smaller))
        return 1.0 if len(token) >= 6 else 0.0
    return len(overlap) / len(smaller)


def _find_fuzzy_duplicate_canonical(name: str, canonical_names: list[str]) -> str | None:
    """Substring, superposición de palabras clave, similitud de texto -- en
    ese orden de confianza. NO incluye la igualdad exacta (el caller la
    resuelve aparte, sin la guardia de dependencia circular, porque dos
    ítems con el nombre EXACTAMENTE igual son por definición el mismo hito,
    nunca un disparador y su propio dependiente)."""
    target = _normalize(name)
    if not target:
        return None
    for canonical in canonical_names:
        candidate = _normalize(canonical)
        if candidate and (target in candidate or candidate in target):
            return canonical
    target_tokens = _significant_tokens(target)
    best_match: str | None = None
    best_ratio = _TOKEN_OVERLAP_THRESHOLD
    for canonical in canonical_names:
        ratio = _token_overlap_ratio(target_tokens, _significant_tokens(_normalize(canonical)))
        if ratio >= best_ratio:
            best_ratio = ratio
            best_match = canonical
    if best_match is not None:
        return best_match
    best_diff: str | None = None
    best_diff_ratio = _FUZZY_MATCH_THRESHOLD
    for canonical in canonical_names:
        ratio = difflib.SequenceMatcher(None, target, _normalize(canonical)).ratio()
        if ratio >= best_diff_ratio:
            best_diff_ratio = ratio
            best_diff = canonical
    return best_diff


def _would_create_circular_dependency(a: dict, b: dict) -> bool:
    """Nunca fusionar un disparador con su propio dependiente. Bug real ya
    documentado en `timeline/materializer.py` (pliego Banco de Córdoba,
    2026-09-01): "Soporte de Migraciones" (un hito) y "Inicio de la Tercera
    Etapa de Migraciones con Soporte" (su disparador) son dos hitos
    distintos, pero el nombre corto del primero está totalmente contenido,
    token por token, en el nombre largo del segundo -- fusionarlos deja un
    plazo circular (mismo trigger que target) y pierde la relación entera.
    Por eso los tiers de similitud ahí NUNCA se prueban contra ítems de la
    misma corrida -- acá, al consolidar DENTRO de una misma corrida, la
    protección tiene que ser explícita: si uno es el disparador del otro,
    nunca se fusionan, sin importar cuánto se parezcan sus nombres."""
    return a.get("nombre") == b.get("evento_disparador") or b.get("nombre") == a.get("evento_disparador")


def _merge_hito_pair(primary: dict, secondary: dict) -> dict:
    merged = dict(primary)

    if not merged.get("fecha_explicita") and secondary.get("fecha_explicita"):
        merged["nombre"] = secondary.get("nombre")
    elif len(str(secondary.get("nombre") or "")) > len(str(merged.get("nombre") or "")):
        merged["nombre"] = secondary.get("nombre")

    for key in ("fecha_explicita", "evento_disparador", "cantidad", "unidad", "tipo_dias", "direccion"):
        if merged.get(key) is None and secondary.get(key) is not None:
            merged[key] = secondary.get(key)
    if secondary.get("es_plazo_maximo"):
        merged["es_plazo_maximo"] = True
    if secondary.get("mencion_propia"):
        merged["mencion_propia"] = True

    primary_frag = str(merged.get("fuente_fragmento") or "").strip()
    secondary_frag = str(secondary.get("fuente_fragmento") or "").strip()
    if secondary_frag and secondary_frag not in primary_frag:
        merged["fuente_fragmento"] = (
            f"{primary_frag} | {secondary_frag}" if primary_frag else secondary_frag
        )
    return merged


def _consolidate_duplicate_hitos(items: list[dict]) -> list[dict]:
    canonical_order: list[str] = []
    groups: dict[str, list[dict]] = {}

    for item in items:
        nombre = item.get("nombre") or ""
        normalized_nombre = _normalize(nombre)
        matched: str | None = None
        for canonical in canonical_order:
            if _normalize(canonical) == normalized_nombre:
                matched = canonical
                break
        if matched is None:
            candidate = _find_fuzzy_duplicate_canonical(nombre, canonical_order)
            if candidate is not None and not any(
                _would_create_circular_dependency(item, member) for member in groups[candidate]
            ):
                matched = candidate
        if matched is None:
            canonical_order.append(nombre)
            groups[nombre] = [item]
        else:
            groups[matched].append(item)

    merged_items: list[dict] = []
    rename_map: dict[str, str] = {}
    for group in groups.values():
        merged = group[0]
        for extra in group[1:]:
            merged = _merge_hito_pair(merged, extra)
        canonical_nombre = merged.get("nombre")
        for member in group:
            original_name = member.get("nombre")
            if original_name and original_name != canonical_nombre:
                rename_map[original_name] = canonical_nombre
        merged_items.append(merged)

    if rename_map:
        for item in merged_items:
            disparador = item.get("evento_disparador")
            if disparador in rename_map:
                item["evento_disparador"] = rename_map[disparador]

    return merged_items


# Agrupa por compartir el mismo `fuente_fragmento` (nombres totalmente distintos, no
# similitud de texto). 3 condiciones para no confundir con garantía+firma en la misma
# oración o disparador+dependiente: substring literal + sin dependencia circular +
# tramo corto del texto (calibrado en 3 casos reales de Bancor: ~45/~114/~74 chars).
_MIN_ENUMERATED_NAME_LEN = 5
_MAX_ENUMERATED_SPAN = 55


def _enumerated_match_span(normalized_fragmento: str, normalized_names: list[str]) -> int | None:
    starts: list[int] = []
    ends: list[int] = []
    for name in normalized_names:
        idx = normalized_fragmento.find(name)
        if idx == -1:
            return None
        starts.append(idx)
        ends.append(idx + len(name))
    return max(ends) - min(starts)


def _merge_enumerated_fragment_duplicates(items: list[dict]) -> list[dict]:
    by_fragmento: dict[str, list[dict]] = {}
    for item in items:
        fragmento = item.get("fuente_fragmento")
        if fragmento:
            by_fragmento.setdefault(fragmento, []).append(item)

    to_merge_ids: set[int] = set()
    replacements: list[dict] = []
    for fragmento, group in by_fragmento.items():
        if len(group) < 2:
            continue
        normalized_fragmento = _normalize(fragmento)
        candidates = [
            item
            for item in group
            if len(_normalize(item.get("nombre") or "")) >= _MIN_ENUMERATED_NAME_LEN
            and _normalize(item.get("nombre") or "") in normalized_fragmento
        ]
        if len(candidates) < 2:
            continue
        eligible = [
            item
            for item in candidates
            if not any(_would_create_circular_dependency(item, other) for other in candidates if other is not item)
        ]
        if len(eligible) < 2:
            continue
        span = _enumerated_match_span(
            normalized_fragmento, [_normalize(item.get("nombre") or "") for item in eligible]
        )
        if span is None or span > _MAX_ENUMERATED_SPAN:
            continue
        combined_nombre = " / ".join(dict.fromkeys(item.get("nombre") for item in eligible))
        merged = dict(eligible[0])
        merged["nombre"] = combined_nombre
        for extra in eligible[1:]:
            for key in ("fecha_explicita", "evento_disparador", "cantidad", "unidad", "tipo_dias", "direccion"):
                if merged.get(key) is None and extra.get(key) is not None:
                    merged[key] = extra.get(key)
            if extra.get("es_plazo_maximo"):
                merged["es_plazo_maximo"] = True
        to_merge_ids.update(id(item) for item in eligible)
        replacements.append(merged)

    result = [item for item in items if id(item) not in to_merge_ids]
    result.extend(replacements)
    return result


def _filter_non_hitos(items: list[dict]) -> list[dict]:
    # Consolida duplicados primero para que el resto del pipeline opere sobre nombres finales.
    # NO se llama acá `_consolidate_duplicate_hitos` (más abajo): fusionaba "Adjudicación"/
    # "Preadjudicación" y "Cumplimiento"/"Vencimiento del Contrato" -- mismo algoritmo seguro
    # en timeline/materializer.py (reconcilia contra corrida ya revisada) es agresivo acá.
    items = _merge_enumerated_fragment_duplicates(items)

    cleaned = [_strip_dangling_disparador(item) for item in items]

    def _apply_reference_aware_filters(candidates: list[dict]) -> list[dict]:
        return [
            item
            for item in candidates
            if not _is_irrelevant_hito(item, candidates)
            and not _is_orphan_non_self_mentioned(item, candidates)
        ]

    survivors = _apply_reference_aware_filters(cleaned)
    # Segunda pasada: 2 ítems irrelevantes pueden protegerse mutuamente vía evento_disparador (caso real Bancor).
    return _apply_reference_aware_filters(survivors)


# Resuelve duplicados con nombres completamente distintos (map-reduce redacta el mismo
# hito distinto en cada lote): similitud de texto puro no es segura para este vocabulario,
# por eso es un paso de síntesis LLM que decide semánticamente (mismo patrón que riesgos.py).
_MAX_DUPLICATE_REDUCE_ITEMS = 60
_MAX_DUPLICATE_DIGEST_CHARS = 220

_DUPLICATE_REDUCE_PROMPT = """Te doy una lista de hitos temporales ya extraídos de UN pliego de licitación. Como se extrajeron en llamados independientes sobre distintas secciones del documento, el MISMO hito real puede haber quedado registrado más de una vez, con nombres o redacciones distintas.

Ejemplo de lo que SÍ es el mismo hito (fusionar): "Apertura de Ofertas" y "Acto de Apertura" -- ambos nombran el mismo momento puntual del proceso.
Ejemplo de lo que NO es el mismo hito (no fusionar): "Adjudicación" y "Preadjudicación" son dos etapas distintas del proceso aunque compartan la raíz de la palabra; "Cumplimiento del Contrato" y "Vencimiento del Contrato" son conceptos opuestos aunque compartan casi todas las palabras.

Hitos extraídos (cada uno con su índice, nombre y la cita textual que lo respalda):
{digest}

Agrupá SOLO los índices que sean la MISMA ocurrencia real mencionada más de una vez -- nunca por vocabulario compartido, nunca por pertenecer a la misma etapa general. Ante la duda, no agrupes.

Devolvé SOLO JSON con esta forma exacta: {{"grupos": [[0, 3], [5, 6, 7]]}} -- una lista por cada grupo de 2 o más índices que sean el mismo hito. Si ningún hito se repite, devolvé {{"grupos": []}}."""


def _build_duplicate_digest(items: list[dict]) -> list[dict]:
    digest = []
    for index, item in enumerate(items):
        cita = str(item.get("fuente_fragmento") or "").strip()
        if len(cita) > _MAX_DUPLICATE_DIGEST_CHARS:
            cita = cita[:_MAX_DUPLICATE_DIGEST_CHARS].rstrip() + "..."
        digest.append({"index": index, "nombre": item.get("nombre"), "cita": cita})
    return digest


def _valid_duplicate_group(raw_group: object, items: list[dict], assigned: set[int]) -> list[int]:
    if not isinstance(raw_group, list):
        return []
    indices = sorted(
        {
            idx
            for idx in raw_group
            if isinstance(idx, int) and 0 <= idx < len(items) and idx not in assigned
        }
    )
    if len(indices) < 2:
        return []
    group_items = [items[idx] for idx in indices]
    for i, a in enumerate(group_items):
        for b in group_items[i + 1 :]:
            if _would_create_circular_dependency(a, b):
                # Nunca fusionar un disparador con su propio dependiente, aunque el LLM lo sugiera.
                return []
    return indices


def _consolidate_duplicates_via_llm(items: list[dict], correlation_id: str) -> list[dict]:
    if len(items) < 2 or len(items) > _MAX_DUPLICATE_REDUCE_ITEMS:
        return items

    digest = _build_duplicate_digest(items)
    prompt = _DUPLICATE_REDUCE_PROMPT.format(
        digest=json.dumps(digest, ensure_ascii=False, indent=2)
    )
    messages = [
        (
            "system",
            "Identificás duplicados semánticos entre hitos temporales ya "
            "extraídos de un pliego de licitación. Devolvés solo JSON válido.",
        ),
        ("human", prompt),
    ]

    try:
        parsed, _usage = _call_llm(messages, correlation_id=f"{correlation_id}-dup-reduce")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "eventos_temporales_duplicate_reduce_failed",
            correlation_id=correlation_id,
            error=str(exc)[:200],
        )
        return items

    raw_groups = parsed.get("grupos")
    if not isinstance(raw_groups, list):
        return items

    assigned: set[int] = set()
    resolved_groups: list[list[int]] = []
    for raw_group in raw_groups:
        indices = _valid_duplicate_group(raw_group, items, assigned)
        if not indices:
            continue
        assigned.update(indices)
        resolved_groups.append(indices)

    if not resolved_groups:
        return items

    rename_map: dict[str, str] = {}
    result = [item for idx, item in enumerate(items) if idx not in assigned]
    for indices in resolved_groups:
        group_items = [items[idx] for idx in indices]
        merged = group_items[0]
        for extra in group_items[1:]:
            merged = _merge_hito_pair(merged, extra)
        canonical_nombre = merged.get("nombre")
        for member in group_items:
            original_name = member.get("nombre")
            if original_name and original_name != canonical_nombre:
                rename_map[original_name] = canonical_nombre
        result.append(merged)

    if rename_map:
        for item in result:
            disparador = item.get("evento_disparador")
            if disparador in rename_map:
                item["evento_disparador"] = rename_map[disparador]

    logger.info(
        "eventos_temporales_duplicates_consolidated",
        correlation_id=correlation_id,
        items_before=len(items),
        items_after=len(result),
        grupos_aplicados=len(resolved_groups),
    )
    return result


def extractor_eventos_temporales(state: GraphState) -> GraphState:
    correlation_id = str(state.get("correlation_id", "eventos_temporales"))
    delta = run_extractor(
        state=state,
        result_key="eventos_temporales",
        state_field="eventos_temporales",
        status_field="eventos_temporales_status",
        prompt_file_name="eventos_temporales.txt",
        query=_QUERY,
    )
    items = delta.get("eventos_temporales")
    if items:
        items = _filter_non_hitos(items)
        items = _consolidate_duplicates_via_llm(items, correlation_id)
        delta["eventos_temporales"] = items
    return delta
