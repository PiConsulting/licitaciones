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


# Historia 25.2: mapeo dominio de email -> business_unit para JIT provisioning vía SSO.
# TODO: agregar dominio de Korex (tenant CEDI) cuando se confirme.
EMAIL_DOMAIN_BUSINESS_UNITS: dict[str, str] = {
    "piconsulting.com.ar": "PI",
    "cedi.com.ar": "CEDI",
    "wemox.com.ar": "Wemox",
    "vulps.com.ar": "Vulps",
}


def business_unit_for_email_domain(email: str) -> str | None:
    domain = email.rsplit("@", 1)[-1].strip().lower()
    candidate = EMAIL_DOMAIN_BUSINESS_UNITS.get(domain)
    return normalize_business_unit(candidate)
