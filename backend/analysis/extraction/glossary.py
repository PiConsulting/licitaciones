from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict[str, list[str]]]:
    glossary_path = Path(__file__).resolve().parent / "glossary.json"
    with glossary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def get_category_terms(category_key: str) -> list[str]:
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return []
    query_terms = entry.get("query_terms", [])
    aliases = entry.get("aliases", [])
    combined = [*query_terms, *aliases]
    return _dedupe_preserve_order([str(item) for item in combined if isinstance(item, str)])


def build_keyword_query(category_key: str) -> str:
    """Construye una query de keywords para BM25: solo los términos
    discriminantes del glossary, sin oraciones largas ni stopwords."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return ""
    query_terms = entry.get("query_terms", [])
    aliases = entry.get("aliases", [])
    terms = _dedupe_preserve_order([str(t) for t in [*query_terms, *aliases] if isinstance(t, str)])
    return " ".join(terms)


def build_prompt_glossary_block(category_key: str) -> str:
    """Genera un bloque de sinónimos para inyectar en el prompt del LLM."""
    terms = get_category_terms(category_key)
    if not terms:
        return ""
    lines = [f"- {term}" for term in terms]
    return "\n".join(lines)


def get_category_top_k(category_key: str, default: int = 25) -> int:
    """Obtiene el top_k configurado para una categoría en glossary.json."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    top_k = entry.get("top_k", default)
    return int(top_k) if isinstance(top_k, (int, float, str)) and str(top_k).isdigit() else default


# FIX (2026-09-03, Fase 1.4 del plan RAG): category_penalty configurable por
# categoría, mismo patrón que get_category_top_k de arriba. Origen: el
# dataset de evaluación (evaluation/datasets/retrieval_eval_v1.json, 9 casos
# / 6 pliegos) mostró que el penalty default de -30% (`chunk_retrieval.py`)
# perjudica activamente el recall de `preview_criterios` en chunks con
# contenido multi-categoría (comportamiento monotónico y reproducible en
# Bancor, Nucleoeléctrica y Bancor/Imperva: a menor penalty, mejor recall,
# sin degradar ningún caso de control) -- pero esa evidencia sólo cubre
# `preview_criterios` y `plazos_clave` (2 de 11 categorías). En vez de bajar
# el default global (que afectaría a 9 categorías sin datos que lo validen),
# se sobreescribe puntualmente por categoría acá, igual que ya se hace con
# `top_k`. Ver docs/docu/PLAN-fix-preview-criterios-y-hardcodeo-rag.md,
# sección 1.4, para el detalle del experimento.
def get_category_penalty(category_key: str, default: float = 0.30) -> float:
    """Obtiene el category_penalty configurado para una categoría en
    glossary.json. Si la categoría no define un override, devuelve `default`
    (el mismo default de producción que ya tenía
    `_retrieve_with_category_priority`)."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    penalty = entry.get("category_penalty", default)
    if isinstance(penalty, bool):
        return default
    if isinstance(penalty, (int, float)):
        return float(penalty)
    if isinstance(penalty, str):
        try:
            return float(penalty)
        except ValueError:
            return default
    return default


def get_category_relevance_min_chunks(category_key: str, default: int = 10) -> int:
    """Obtiene el piso de chunks por categoría para el corte de relevancia.

    Mantiene el comportamiento actual por default y permite override puntual
    en glossary.json (mismo patrón que top_k/category_penalty).
    """
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("relevance_min_chunks", default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(1, value)
    if isinstance(value, float) and value.is_integer():
        return max(1, int(value))
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            return max(1, int(cleaned))
    return default


def get_category_relevance_min_ratio(category_key: str, default: float = 0.4) -> float:
    """Obtiene el ratio de corte de relevancia por categoría.

    Si no hay override o no es coercible a float, mantiene el default.
    """
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("relevance_min_ratio", default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def get_category_rank_fusion(category_key: str, default: bool = False) -> bool:
    """Override por categoría: en `_score_chunks_for_category`, fusionar el
    ranking híbrido con un ranking propio de la señal de categoría vía RRF
    (scale-free), en vez del boost multiplicativo. Ataca la Causa 2 de la
    auditoría de ranking (2026-09-09): scores RRF planos donde el
    multiplicativo no separa gold de ruido. Opt-in por si ayuda a unas
    categorías y no a otras (patrón de toda la sesión)."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("rank_fusion", default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "si", "sí"}
    return default


def get_category_graded_scores(category_key: str, default: bool = False) -> bool:
    """Override por categoría: usar el vector `category_scores` (multi-label)
    para un boost GRADUADO en el retrieval, en vez del boost binario
    primary/secondary. Medido (2026-09-09): el graduado ayuda mucho a
    categorías con gold disperso/multi-categoría (`requisitos_admisibilidad`
    +0.167, `plazos_clave` +0.03) y PERJUDICA a las de gold limpio y
    concentrado (`anexos_obligatorios` −0.10, promueve chunks semánticamente
    vecinos). Por eso es opt-in por categoría."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("graded_category_scores", default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "si", "sí"}
    return default


def get_category_self_consistency_runs(category_key: str, default: int = 1) -> int:
    """Override por categoría: cuántas veces repetir el llamado LLM de cada
    grupo del map-reduce (Fase 2 de la auditoría RAG, 2026-09-14). Diagnóstico
    que lo motiva: con el chunking ya arreglado (headings/incisos, P0-1), el
    gap que queda en garantías/requisitos_admisibilidad/identificacion_
    procedimiento/riesgos no es de chunking ni de retrieval -- es que el LLM,
    frente a una cláusula con varios datos (ej. "exento si no supera $40M" +
    "forma: póliza electrónica"), saca uno y descarta el otro, de forma no
    determinista entre corridas (ver comentario de `seed` en
    `infra/adapters/azure_openai.py`). Repetir el llamado y dejar que el
    dedup de `merge_node` (ya existe, agrupa por categoría) una los ítems de
    ambas corridas -- un ítem que aparece en CUALQUIER corrida sobrevive, en
    vez de depender de que una sola corrida lo haya sacado todo. 1 = sin
    cambios (default). Opt-in por categoría porque duplica el costo/latencia
    de las categorías donde se activa -- no hacerlo global sin medir."""
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("self_consistency_runs", default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def get_category_query_expansion(category_key: str, default: bool = False) -> bool:
    """Override por categoría de la expansión de query con definición
    semántica (mismo patrón que top_k/category_penalty).

    Motivo (2026-09-09): medido sobre 76 casos, activar el flag GLOBAL
    `QUERY_EXPANSION_USE_SEMANTIC_DEFINITION` da resultado mixto -- `riesgos`
    +0.144 de recall efectivo, pero `anexos_obligatorios` -0.063 y `garantias`
    -0.024. Sirve donde la frase corta del extractor es vaga (riesgos), daña
    donde ya es precisa. Por eso se habilita por categoría acá en vez de
    global. `run_extractor` (base.py) y `measure_recall.py` consultan ESTE
    override además del flag global.
    """
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    value = entry.get("query_expansion", default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "si", "sí"}
    return default


# FASE 4 del plan RAG v2 (2026-08-24, sección 4.4): query expansion con
# definición semántica. `category_definitions.json` ya existe desde la Fase 2
# (4.3, clasificación semántica de chunks) -- acá se reutiliza la misma
# definición versionada, no se inventa una segunda fuente de verdad.
@lru_cache(maxsize=1)
def _load_category_definitions() -> dict[str, dict]:
    """Carga category_definitions.json (mismo archivo que usa
    extraction/chunking.py para el fallback semántico de clasificación).
    Degrada a `{}` si el archivo no existe o es inválido -- la expansión de
    query es un enriquecimiento opcional, nunca debe tumbar el retrieval."""
    definitions_path = Path(__file__).resolve().parent / "category_definitions.json"
    if not definitions_path.exists():
        return {}
    try:
        with definitions_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and k != "_comment"}


def build_semantic_expanded_query(category_key: str, base_query: str) -> str:
    """Enriquece la query que se vectoriza para el vector search (`query` en
    `_retrieve_with_category_priority`) con la definición semántica completa
    de la categoría, en vez de dejarla solo con la frase corta que arma cada
    rama del extractor.

    No reemplaza `base_query`: lo antepone como contexto conceptual y agrega
    la frase original a continuación, para no perder matices específicos que
    algún extractor ya haya afinado a mano. Si no hay definición para la
    categoría (archivo ausente, entrada faltante), devuelve `base_query` sin
    cambios -- este enriquecimiento es aditivo y nunca debe dejar la query
    vacía ni distinta de la original cuando no hay nada que agregar."""
    definitions = _load_category_definitions()
    entry = definitions.get(category_key)
    if not entry:
        return base_query
    definition = entry.get("definition")
    if not isinstance(definition, str) or not definition.strip():
        return base_query
    definition = definition.strip()
    base_query = (base_query or "").strip()
    if not base_query:
        return definition
    if definition in base_query:
        # Ya está incluida (p.ej. si en el futuro algún extractor arma su
        # `_QUERY` copiando la definición) -- no duplicar.
        return base_query
    return f"{definition}\n\n{base_query}"
