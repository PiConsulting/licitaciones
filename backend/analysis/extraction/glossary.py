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
    """Obtiene el top_k configurado para una categoría en glossary.json.
    """
    glossary = _load_glossary()
    entry = glossary.get(category_key, {})
    if not isinstance(entry, dict):
        return default
    top_k = entry.get("top_k", default)
    return int(top_k) if isinstance(top_k, (int, float, str)) and str(top_k).isdigit() else default
