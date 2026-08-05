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


def build_query_from_glossary(category_key: str, fallback_query: str) -> str:
    """Combina query del extractor con sinonimos del glosario sin descartar ninguna."""
    terms = get_category_terms(category_key)
    combined = [fallback_query.strip(), *terms]
    return " ".join(part for part in combined if part).strip()


def build_prompt_glossary_block(category_key: str) -> str:
    terms = get_category_terms(category_key)
    if not terms:
        return ""
    lines = [f"- {term}" for term in terms]
    return "\n".join(lines)
