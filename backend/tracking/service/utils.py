"""Utilidades chicas y sin dependencias: parseo de fechas y normalizacion de texto para hashing determinista."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


TRACKING_CATEGORY_KEYS = [
    "objeto_alcance",
    "requisitos_admisibilidad",
    "garantias",
    "plazos_clave",
    "criterios_evaluacion",
    "causales_rechazo",
    "anexos_obligatorios",
]

ACTIONABLE_CHECKLIST_CATEGORIES = {"requisitos_admisibilidad", "anexos_obligatorios"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
