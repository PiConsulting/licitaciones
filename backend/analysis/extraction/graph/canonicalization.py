"""Normalizacion de texto libre a valores canonicos (tipos de garantia, identificacion, causal, riesgo) para poder deduplicar items del LLM."""
from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

_TIPOS_IDENTIFICACION_VALIDOS = {
    "organismo_convocante",
    "expediente",
    "numero_procedimiento",
    "tipo_procedimiento",
    "presupuesto_oficial",
    "jurisdiccion",
    "denominacion",
}


def _merge_category_status(*statuses: str) -> str:
    pool = {str(status or "").strip() for status in statuses}
    if "success" in pool:
        return "success"
    if "partial" in pool:
        return "partial"
    if "not_applicable" in pool:
        return "not_applicable"
    if "not_found" in pool:
        return "not_found"
    if "failed" in pool:
        return "failed"
    return "unknown"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _normalized_referencia_key(item: dict) -> str:
    """Huella de texto de a qué plazo se refiere un ítem, usada para agrupar
    (dedup y detección de conflictos) sin depender de una taxonomía fija.

    FIX (2026-08-22): reemplaza a la vieja `_canonical_plazo_tipo`, que
    forzaba cada plazo a uno de 17 valores de enum y, para todo lo que no
    calzaba con esas palabras clave, devolvía `"otro"` -- en la práctica eso
    era la mayoría de los ítems. El resultado: plazos sin ninguna relación
    entre sí quedaban agrupados bajo el mismo balde `"otro"`, lo que además de
    no decir nada en la UI generaba falsos "conflictos" (ver más abajo, donde
    se agrupaba por tipo para detectar fechas distintas del mismo hito).
    Ahora se agrupa por el propio `referencia` que puso el LLM -- texto libre,
    no enum -- normalizado para que variaciones menores de redacción no
    rompan el agrupamiento.
    """
    return _normalize_text(str(item.get("referencia") or ""))


def _canonical_garantia_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otra"

    if "cumplimiento" in text and "contrato" in text:
        return "cumplimiento_contrato"
    if "anticipo" in text:
        return "anticipo"
    if (
        "mantenimiento" in text
        or "seriedad" in text
        or ("garantia" in text and "oferta" in text)
        or ("caucion" in text and "oferta" in text)
        or ("fianza" in text and "oferta" in text)
    ):
        return "mantenimiento_oferta"
    return "otra"


def _canonical_identificacion_tipo(value: str) -> str | None:
    """Mapea el `tipo` que devuelve el LLM al enum `TipoIdentificacion`.
    Devuelve None si no corresponde a ninguno: esos ítems no pueden ir al campo
    canónico (pydantic los rechazaría y tumbaría merge_node entero), pero sí
    sobreviven en el campo legacy `datos_procedimiento`, que acepta tipo libre."""
    text = _normalize_text(value)
    if not text:
        return None
    if text in _TIPOS_IDENTIFICACION_VALIDOS:
        return text
    if "organismo" in text or "convocante" in text:
        return "organismo_convocante"
    if "expediente" in text:
        return "expediente"
    if "presupuesto" in text:
        return "presupuesto_oficial"
    if "jurisdicc" in text:
        return "jurisdiccion"
    if "denomina" in text or "nombre del llamado" in text or "nombre_del_llamado" in text:
        return "denominacion"
    if "proced" in text:
        if "tipo" in text:
            return "tipo_procedimiento"
        return "numero_procedimiento"
    return None


def _canonical_causal_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otra"

    if any(term in text for term in ["formal", "document", "garantia", "presentacion", "termino"]):
        return "formal"
    if any(term in text for term in ["tecnic", "especificacion", "muestra"]):
        return "tecnica"
    if any(term in text for term in ["econom", "precio", "cotizacion"]):
        return "economica"
    if any(term in text for term in ["legal", "inhabilit", "registro", "juridic"]):
        return "legal"

    return "otra"


def _canonical_riesgo_subtipo(value: str) -> str:
    """Normaliza el subtipo de riesgo al enum canónico.

    Mapea variaciones textuales del LLM a los valores del enum SubtipoRiesgo.
    Si no se puede clasificar con confianza, devuelve 'otro_explicito'.

    IMPORTANTE: El orden de evaluación importa - los términos más específicos
    van primero para evitar falsos positivos con términos genéricos.
    """
    text = _normalize_text(value)
    if not text:
        return "otro_explicito"
    
    # Comercial (muy específico - primero)
    if any(
        term in text
        for term in [
            "mantenimiento oferta",
            "mantener oferta",
            "vigencia oferta",
            "moneda",
            "tipo cambio",
            "cambiario",
            "forma pago",
            "forma de pago",
            "competencia",
            "competidor",
            "competitiv",
            "cuenta bancaria",
            "apertura cuenta",
            "control cuenta",
            "presentacion presencial",
            "apertura fisica",
            "certificacion",
            "skill",
            "capacidad tecnica",
            "experiencia minima",
        ]
    ):
        return "comercial"
    
    if any(term in text for term in ["incumplimiento", "incumplir", "falta", "omision"]):
        return "incumplimiento"
    if any(term in text for term in ["plazo", "demora", "retraso", "vencimiento", "termino"]):
        return "plazos"
    if any(
        term in text
        for term in ["econom", "financier", "multa", "penaliza", "sancion monetaria", "pago"]
    ):
        return "economico"
    if any(term in text for term in ["tecnic", "especificacion", "calidad", "norma tecnica"]):
        return "tecnico"
    if any(term in text for term in ["legal", "contractual", "juridic", "rescision", "clausula"]):
        return "legal_contractual"
    if any(term in text for term in ["operativ", "gestion", "administra", "logistic"]):
        return "operativo"
    if any(term in text for term in ["ejecucion", "ejecutar", "cumplir contrato", "entrega"]):
        return "ejecucion"

    return "otro_explicito"


def _plazo_dedup_value(item: dict) -> str:
    """Huella del "valor" de un plazo, para no fusionar dos plazos del mismo
    tipo que en realidad dicen cosas distintas (eso es un conflicto, no un
    duplicado). Normaliza el texto para que variaciones menores se reconozcan
    como duplicados (ej: '12 meses' vs '12 (doce) meses')."""
    raw_value = str(
        item.get("fecha") or item.get("expresion_relativa") or item.get("texto_original") or ""
    )
    normalized = _normalize_text(raw_value)
    normalized = re.sub(r"\(\w+\)", "", normalized).strip()
    normalized = " ".join(normalized.split())
    return normalized


def _garantia_dedup_value(item: dict) -> str:
    return f"{item.get('monto_porcentaje')}|{item.get('monto_valor')}"
