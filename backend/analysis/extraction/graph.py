from __future__ import annotations

from collections import defaultdict
from typing import Callable
import unicodedata

import structlog
from langgraph.graph import END, StateGraph

from analysis.extraction.extractors import (
    extractor_anexos_obligatorios,
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_garantias,
    extractor_identificacion_procedimiento,
    extractor_objeto_alcance,
    extractor_plazos,
    extractor_requisitos_admisibilidad,
)
from analysis.extraction.schemas import ExtractedData
from analysis.extraction.state import GraphState
from analysis.extraction.synthesis import NARRATIVE_CATEGORIES, run_synthesis

logger = structlog.get_logger(__name__)


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


def _canonical_plazo_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otro"

    if "respuesta" in text and "consulta" in text:
        return "respuesta_consultas"
    if "consulta" in text:
        return "consultas"
    if "visita" in text and "obra" in text:
        return "visita_lugar"
    if "apertura" in text:
        return "apertura_ofertas"
    if "mantenimiento" in text and "oferta" in text:
        return "mantenimiento_oferta"
    if "adjudic" in text:
        return "adjudicacion"
    if "firma" in text and "contrato" in text:
        return "firma_contrato"
    if "impugn" in text:
        return "impugnacion"
    if (
        "presentacion de ofertas" in text
        or "cierre de recepcion de ofertas" in text
        or "fecha limite de presentacion" in text
        or ("presentacion" in text and "oferta" in text)
        or ("recepcion" in text and "oferta" in text)
    ):
        return "presentacion_ofertas"
    return "otro"


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
    if any(term in text for term in ["etica", "conflicto", "corrup", "integridad"]):
        return "etica"
    return "otra"


def _plazo_dedup_value(item: dict) -> str:
    """Huella del "valor" de un plazo, para no fusionar dos plazos del mismo
    tipo que en realidad dicen cosas distintas (eso es un conflicto, no un
    duplicado)."""
    return str(item.get("fecha") or item.get("expresion_relativa") or item.get("texto_original") or "")


def _garantia_dedup_value(item: dict) -> str:
    return f"{item.get('monto_porcentaje')}|{item.get('monto_valor')}"


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

    # Completa campos que el primario dejó vacíos con lo que traigan los demás
    # ítems del grupo, sin pisar ningún valor que el primario sí tenga.
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


def _merge_duplicate_typed_items(items: list[dict], dedup_value: Callable[[dict], str]) -> list[dict]:
    return _merge_duplicate_items_by_key(items, lambda item: (str(item.get("tipo", "")), dedup_value(item)))


def _normalized_valor_key(item: dict) -> str:
    """Huella de texto para detectar el mismo hecho extraido dos veces con
    redaccion casi identica (tipico cuando el mismo parrafo cae en dos chunks
    solapados). Solo normaliza espacios/mayusculas -- deliberadamente NO hace
    matching difuso (por substring o similitud) para no fusionar por error dos
    hechos distintos que comparten palabras."""
    return " ".join(str(item.get("valor", "")).split()).strip().lower()


def calculate_confidence(source_references: list[dict], extraction_status: str) -> float:
    if extraction_status in {"failed", "not_found"}:
        return 0.0

    if extraction_status == "not_applicable":
        return 0.7 if source_references else 0.0

    if not source_references:
        return 0.3

    confidence = 0.5
    if len(source_references) > 1:
        confidence += 0.3
    elif len(source_references) == 1:
        confidence += 0.2

    if source_references:
        avg_citation_length = sum(len(str(ref.get("citation", ""))) for ref in source_references) / len(source_references)
        if avg_citation_length > 100:
            confidence += 0.2
        elif avg_citation_length < 25:
            confidence -= 0.2

    if extraction_status == "partial":
        confidence -= 0.2

    return max(0.0, min(confidence, 1.0))


def get_confidence_level(confidence: float) -> str:
    if confidence >= 0.8:
        return "alta"
    if confidence >= 0.6:
        return "media"
    return "baja"


def _normalize_confidence(item: dict) -> dict:
    status = str(item.get("extraction_status", "success"))
    refs = list(item.get("source_references", []))
    if "confidence" not in item:
        item["confidence"] = calculate_confidence(refs, status)
    else:
        conf = float(item.get("confidence", 0.0) or 0.0)
        item["confidence"] = max(0.0, min(conf, 1.0))
    item["confidence_level"] = get_confidence_level(float(item.get("confidence", 0.0) or 0.0))
    return item


def _penalize_unverifiable(item: dict) -> dict:
    """Marca como partial los items sin citas verificables. El minimo (40)
    coincide con el que exige _base_system.txt (regla 5) -- si el LLM manda una
    cita mas corta que eso, el prompt ya la considera invalida, asi que el
    backstop de codigo tiene que usar el mismo piso."""
    refs = list(item.get("source_references", []))
    status = str(item.get("extraction_status", ""))
    if status in {"success", "partial"}:
        usable = [ref for ref in refs if len(str(ref.get("citation", "")).strip()) >= 40]
        if not usable:
            item["extraction_status"] = "partial"
            item["_warning"] = "cita_insuficiente"
    return item


def _category_confidence(items: list[dict]) -> float:
    """Calcula un score de confianza agregado para toda la categoría."""
    with_confidence = [
        float(item.get("confidence", 0.0) or 0.0)
        for item in items
        if float(item.get("confidence", 0.0) or 0.0) > 0.0
    ]
    if not with_confidence:
        return 0.0
    return round(sum(with_confidence) / len(with_confidence), 2)


def setup_node(state: GraphState) -> GraphState:
    logger.info("setup_node_started", correlation_id=state["correlation_id"], analysis_id=state["analysis_id"])
    state.update(
        {
            "objeto_alcance": [],
            "objeto_alcance_status": "pending",
            "requisitos_admisibilidad": [],
            "requisitos_admisibilidad_status": "pending",
            "plazos": [],
            "plazos_status": "pending",
            "garantias": [],
            "garantias_status": "pending",
            "causales": [],
            "causales_status": "pending",
            "anexos": [],
            "anexos_status": "pending",
            "criterios": [],
            "criterios_status": "pending",
            "identificacion": [],
            "identificacion_status": "pending",
            "conflicts": [],
        }
    )
    logger.info("setup_node_completed", correlation_id=state["correlation_id"])
    return state


def merge_node(state: GraphState) -> GraphState:
    correlation_id = state["correlation_id"]
    logger.info("merge_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    plazos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("plazos", [])]
    objeto_alcance = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("objeto_alcance", [])]
    requisitos_admisibilidad = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("requisitos_admisibilidad", [])
    ]
    garantias = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("garantias", [])]
    causales = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("causales", [])]
    anexos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("anexos", [])]
    criterios = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("criterios", [])]
    identificacion = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("identificacion", [])]

    # Canonicalizar el tipo ANTES de deduplicar: dos ítems que citan el mismo
    # hecho (ej. "mantenimiento de oferta" extraído de dos fragmentos/documentos
    # distintos) suelen llegar con una redacción de `tipo` levemente distinta, y
    # solo se reconocen como el mismo hecho después de canonicalizar.
    for plazo in plazos:
        plazo["tipo"] = _canonical_plazo_tipo(str(plazo.get("tipo", "")))
    plazos = _merge_duplicate_typed_items(plazos, _plazo_dedup_value)

    for garantia in garantias:
        garantia["tipo"] = _canonical_garantia_tipo(str(garantia.get("tipo", "")))
    garantias = _merge_duplicate_typed_items(garantias, _garantia_dedup_value)

    # Las otras 6 categorías no tienen un `tipo` canonicalizado especial: se
    # deduplican por (tipo tal cual, huella normalizada del valor). El chunker
    # solapa 120 tokens a propósito, así que es común que el mismo hecho quede
    # citado en dos fragmentos distintos que el extractor recupera ambos.
    objeto_alcance = _merge_duplicate_items_by_key(
        objeto_alcance, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    requisitos_admisibilidad = _merge_duplicate_items_by_key(
        requisitos_admisibilidad, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    # causales_rechazo: el único `tipo` posible es "causal_rechazo", así que
    # agrupar con ese campo no distingue nada — se deduplica solo por valor.
    for causal in causales:
        causal["tipo"] = _canonical_causal_tipo(str(causal.get("tipo", "")))
    causales = _merge_duplicate_items_by_key(causales, lambda item: (_normalized_valor_key(item),))
    anexos = _merge_duplicate_items_by_key(
        anexos, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    criterios = _merge_duplicate_items_by_key(
        criterios, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    identificacion = _merge_duplicate_items_by_key(
        identificacion, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )

    extracted_data = {
        "objeto_alcance": objeto_alcance,
        "objeto_alcance_extraction_status": state.get("objeto_alcance_status", "unknown"),
        "objeto_alcance_confidence": _category_confidence(objeto_alcance),
        "requisitos_admisibilidad": requisitos_admisibilidad,
        "requisitos_admisibilidad_extraction_status": state.get("requisitos_admisibilidad_status", "unknown"),
        "requisitos_admisibilidad_confidence": _category_confidence(requisitos_admisibilidad),
        "plazos_clave": plazos,
        "plazos_clave_extraction_status": state.get("plazos_status", "unknown"),
        "plazos_clave_confidence": _category_confidence(plazos),
        "plazos": plazos,
        "plazos_extraction_status": state.get("plazos_status", "unknown"),
        "garantias": garantias,
        "garantias_extraction_status": state.get("garantias_status", "unknown"),
        "garantias_confidence": _category_confidence(garantias),
        "causales_rechazo": causales,
        "causales_extraction_status": state.get("causales_status", "unknown"),
        "causales_rechazo_confidence": _category_confidence(causales),
        "anexos_obligatorios": anexos,
        "anexos_extraction_status": state.get("anexos_status", "unknown"),
        "anexos_obligatorios_confidence": _category_confidence(anexos),
        "datos_procedimiento": identificacion,
        "datos_procedimiento_extraction_status": state.get("identificacion_status", "unknown"),
        "datos_procedimiento_confidence": _category_confidence(identificacion),
        "documentos_requeridos": [],
        "documentos_extraction_status": "not_found",
        "criterios_evaluacion": criterios,
        "criterios_extraction_status": state.get("criterios_status", "unknown"),
        "criterios_evaluacion_confidence": _category_confidence(criterios),
        "restricciones_participacion": [],
        "restricciones_extraction_status": "not_found",
        "cronograma_proceso": [],
        "cronograma_extraction_status": "not_found",
        "estimacion_presupuesto": None,
        "presupuesto_extraction_status": "not_found",
    }

    token_usage = {
        "objeto_alcance": state.get("objeto_alcance_token_usage", {}),
        "requisitos_admisibilidad": state.get("requisitos_admisibilidad_token_usage", {}),
        "plazos_clave": state.get("plazos_token_usage", {}),
        "garantias": state.get("garantias_token_usage", {}),
        "causales_rechazo": state.get("causales_token_usage", {}),
        "anexos_obligatorios": state.get("anexos_token_usage", {}),
        "criterios_evaluacion": state.get("criterios_token_usage", {}),
        "identificacion_procedimiento": state.get("identificacion_token_usage", {}),
    }

    conflicts: list[dict] = []

    plazos_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for plazo in plazos:
        plazos_by_tipo[str(plazo.get("tipo", ""))].append(plazo)

    for tipo, items in plazos_by_tipo.items():
        if tipo and len(items) > 1:
            fechas = {item.get("fecha") for item in items}
            if len(fechas) > 1:
                conflicts.append(
                    {
                        "category": "plazos",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Fechas diferentes en distintos documentos",
                    }
                )

    garantias_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for garantia in garantias:
        garantias_by_tipo[str(garantia.get("tipo", ""))].append(garantia)

    for tipo, items in garantias_by_tipo.items():
        if tipo and len(items) > 1:
            montos = {(item.get("monto_porcentaje"), item.get("monto_valor")) for item in items}
            if len(montos) > 1:
                conflicts.append(
                    {
                        "category": "garantias",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Montos diferentes en distintos documentos",
                    }
                )

    validated = ExtractedData(**extracted_data)
    state["extracted_data"] = validated.model_dump()
    state["conflicts"] = conflicts
    state["extraction_metadata"] = {"token_usage": token_usage}

    logger.info(
        "merge_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        conflicts_count=len(conflicts),
    )
    return state


def synthesize_node(state: GraphState) -> GraphState:
    """Convierte cada categoria ya mergeada en una respuesta de experto (bloques
    en lenguaje natural), una llamada LLM liviana por categoria (no vuelve a
    buscar chunks). Si una categoria falla la sintesis, simplemente no lleva
    `_narrative` en `extracted_data` — el frontend cae a su propio fallback, asi
    que un fallo aca nunca deja una categoria sin respuesta ni tumba el resto."""
    correlation_id = state["correlation_id"]
    logger.info("synthesize_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    extracted_data = state.get("extracted_data", {})
    metadata = state.get("extraction_metadata", {})
    token_usage_by_category = dict(metadata.get("token_usage", {}))

    synthesized = 0
    for category_key in NARRATIVE_CATEGORIES:
        items = extracted_data.get(category_key, [])
        if not isinstance(items, list):
            continue
        result = run_synthesis(category_key=category_key, items=items, correlation_id=correlation_id)
        if result is None:
            continue
        narrative, token_usage = result
        extracted_data[f"{category_key}_narrative"] = narrative.model_dump()
        token_usage_by_category[f"{category_key}_synthesis"] = token_usage
        synthesized += 1

    metadata["token_usage"] = token_usage_by_category
    state["extracted_data"] = extracted_data
    state["extraction_metadata"] = metadata

    logger.info(
        "synthesize_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        categories_synthesized=synthesized,
    )
    return state


builder = StateGraph(GraphState)

builder.add_node("setup", setup_node)
builder.add_node("extract_objeto_alcance", extractor_objeto_alcance)
builder.add_node("extract_plazos", extractor_plazos)
builder.add_node("extract_garantias", extractor_garantias)
builder.add_node("extract_causales", extractor_causales)
builder.add_node("extract_anexos", extractor_anexos_obligatorios)
builder.add_node("extract_requisitos", extractor_requisitos_admisibilidad)
builder.add_node("extract_criterios", extractor_criterios_evaluacion)
builder.add_node("extract_identificacion", extractor_identificacion_procedimiento)
builder.add_node("merge", merge_node)
builder.add_node("synthesize", synthesize_node)

builder.set_entry_point("setup")

extractor_nodes = [
    "extract_objeto_alcance",
    "extract_plazos",
    "extract_garantias",
    "extract_causales",
    "extract_anexos",
    "extract_requisitos",
    "extract_criterios",
    "extract_identificacion",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", "synthesize")
builder.add_edge("synthesize", END)

graph = builder.compile()
