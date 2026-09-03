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
