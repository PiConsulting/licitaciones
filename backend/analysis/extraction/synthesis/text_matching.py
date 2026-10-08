"""Normalizacion y comparacion de texto libre para anclar evidencia del LLM a citas ya verificadas."""
from __future__ import annotations

import unicodedata

import structlog

logger = structlog.get_logger(__name__)


def _normalize_text_for_comparison(text: str) -> str:
    """Normaliza texto para comparación: elimina acentos, espacios múltiples, lowercase."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _overlap_ratio(needle: str, haystack: str) -> float:
    """Fracción de palabras de `needle` presentes en `haystack`. Sólo se usa
    para elegir, entre las citas verificadas de un mismo item, cuál se parece
    más al texto que transcribió el LLM."""
    needle_words = set(_normalize_text_for_comparison(needle).split())
    if not needle_words:
        return 0.0
    haystack_words = set(_normalize_text_for_comparison(haystack).split())
    return len(needle_words & haystack_words) / len(needle_words)
