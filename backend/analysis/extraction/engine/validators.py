"""Validadores para extracción de categorías - detección de contaminación cruzada"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Términos exclusivos de cada categoría que señalan contaminación
CATEGORY_EXCLUSIVE_TERMS = {
    "garantias": [
        "seguro de caucion",
        "poliza",
        "caucion",
        "fianza",
        "mantenimiento de oferta",
        "garantia de oferta",
        "garantia de seriedad",
        "garantia de cumplimiento",
        "aval bancario",
        "deposito en garantia",
    ],
    "anexos_obligatorios": [
        "anexo i",
        "anexo ii",
        "anexo iii",
        "anexo iv",
        "formulario",
        "planilla",
        "modelo de",
    ],
    "plazos_clave": [
        "fecha de apertura",
        "plazo de entrega",
        "cronograma",
        "vencimiento",
    ],
    "criterios_evaluacion": [
        "ponderacion",
        "puntaje tecnico",
        "puntaje economico",
        "precio mas bajo",
        "oferta mas conveniente",
    ],
}


def _normalize_for_detection(text: str) -> str:
    """Normaliza texto para detección (lowercase, sin puntuación extra)"""
    return " ".join(str(text or "").lower().split())


def detect_cross_contamination(items: list[dict], category: str) -> list[dict]:
    """Detecta ítems que contienen información de otras categorías.

    Marca items con `_warning: "cross_contamination"` si:
    - El valor/descripción menciona términos exclusivos de otra categoría
    - Y esos términos NO son válidos para la categoría actual

    Args:
        items: Lista de ítems extraídos
        category: Categoría actual (ej: "requisitos_admisibilidad")

    Returns:
        Lista de ítems contaminados (subconjunto de items)
    """
    contaminated = []

    for item in items:
        if not isinstance(item, dict):
            continue

        valor = str(item.get("valor", ""))
        tipo = str(item.get("tipo", ""))
        combined_text = _normalize_for_detection(f"{tipo} {valor}")

        if not combined_text:
            continue

        for other_category, exclusive_terms in CATEGORY_EXCLUSIVE_TERMS.items():
            if other_category == category:
                continue

            # Verificar si contiene términos de otra categoría
            for term in exclusive_terms:
                normalized_term = _normalize_for_detection(term)
                if normalized_term in combined_text:
                    item["_warning"] = "cross_contamination"
                    item["_contaminated_with"] = other_category
                    item["_contamination_term"] = term
                    contaminated.append(item)
                    break

            # Si ya marcado, no seguir buscando
            if item.get("_warning") == "cross_contamination":
                break

    return contaminated
