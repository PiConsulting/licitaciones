from __future__ import annotations

BUSINESS_UNITS: tuple[str, ...] = ("CEDI", "PI", "Wemox", "Vulps", "Korex")
MAX_BUSINESS_UNIT_LENGTH = 80


def normalize_business_unit(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    return next((unit for unit in BUSINESS_UNITS if unit.lower() == candidate.lower()), None)


def is_valid_business_unit(value: str | None) -> bool:
    return normalize_business_unit(value) is not None
