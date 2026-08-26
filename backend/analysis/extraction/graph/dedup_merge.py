"""Fusion de items duplicados o del mismo tipo detectados via las claves canonicas."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

import structlog

from analysis.extraction.graph.canonicalization import _normalize_text

logger = structlog.get_logger(__name__)


def _dedupe_source_references(refs: list[dict]) -> list[dict]:
    seen: set[tuple[str, int, str]] = set()
    result: list[dict] = []
    for ref in refs:
        key = (
            str(ref.get("document_id", "")),
            int(ref.get("page_number", 0) or 0),
            _normalize_text(str(ref.get("citation", ""))),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _merge_typed_item_group(items: list[dict]) -> dict:
    """Fusiona ítems que citan el mismo hecho (mismo tipo canónico y mismo
    valor identificador) en uno solo, combinando sus citas. Sin esto, un mismo
    plazo o garantía citado desde más de un fragmento/documento queda duplicado
    en la lista final (ej. dos ítems de "mantenimiento de oferta") en vez de
    aparecer una sola vez con todas sus fuentes."""
    primary = max(
        items,
        key=lambda item: (
            1 if item.get("extraction_status") == "success" else 0,
            float(item.get("confidence", 0.0) or 0.0),
        ),
    )
    merged = dict(primary)

    all_refs: list[dict] = []
    for item in items:
        all_refs.extend(item.get("source_references", []))
    merged["source_references"] = _dedupe_source_references(all_refs)
    for item in items:
        for key, value in item.items():
            if key in {"source_references", "confidence", "extraction_status"}:
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value

    return merged


def _merge_duplicate_items_by_key(items: list[dict], key_fn: Callable[[dict], tuple]) -> list[dict]:
    """Version generalizada de _merge_duplicate_typed_items: agrupa por una
    clave arbitraria (no necesariamente tipo + un valor) y fusiona cada grupo
    con _merge_typed_item_group."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    order: list[tuple] = []
    for item in items:
        key = key_fn(item)
        if key not in grouped:
            order.append(key)
        grouped[key].append(item)

    merged: list[dict] = []
    for key in order:
        group = grouped[key]
        merged.append(group[0] if len(group) == 1 else _merge_typed_item_group(group))
    return merged


def _merge_duplicate_typed_items(
    items: list[dict], dedup_value: Callable[[dict], str]
) -> list[dict]:
    return _merge_duplicate_items_by_key(
        items, lambda item: (str(item.get("tipo", "")), dedup_value(item))
    )


def _normalized_valor_key(item: dict) -> str:
    """Huella de texto para detectar el mismo hecho extraido dos veces con
    redaccion casi identica (tipico cuando el mismo parrafo cae en dos chunks
    solapados). Solo normaliza espacios/mayusculas -- deliberadamente NO hace
    matching difuso (por substring o similitud) para no fusionar por error dos
    hechos distintos que comparten palabras."""
    return " ".join(str(item.get("valor", "")).split()).strip().lower()
