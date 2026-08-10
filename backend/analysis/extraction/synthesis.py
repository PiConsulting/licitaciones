from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.extractors import base as extractors_base
from analysis.extraction.schemas import CategoryNarrative

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"

CATEGORY_LABELS = {
    "objeto_alcance": "Objeto y Alcance",
    "requisitos_admisibilidad": "Requisitos de Admisibilidad",
    "garantias": "Garantías",
    "plazos_clave": "Plazos Clave",
    "criterios_evaluacion": "Criterios de Evaluación",
    "causales_rechazo": "Causales de Rechazo",
    "anexos_obligatorios": "Anexos Obligatorios",
}

CATEGORY_OUTPUT_CONTRACTS = {
    "objeto_alcance": (
        "- Devolver exactamente QUE se licita en 2-3 lineas maximo.\n"
        "- No incluir modalidad, lugar de entrega, plazos, garantias, criterios, causales, anexos ni requisitos.\n"
        "- Emitir UN solo bloque `paragraph` con sintesis directa, sin introducciones largas."
    ),
    "requisitos_admisibilidad": (
        "- Devolver solo documentacion obligatoria de admisibilidad (habilitaciones, antecedentes, certificaciones)\n"
        "  cuya falta puede rechazar la oferta de entrada.\n"
        "- Usar `bullet_list` con items cortos y accionables (ideal <= 14 palabras).\n"
        "- Estilo preferido: verbo + documento (ej: 'Presentar constancia RUP vigente')."
    ),
    "garantias": (
        "- Devolver solo garantias financieras (mantenimiento de oferta, cumplimiento de contrato y similares).\n"
        "- Incluir monto/porcentaje y forma de constitucion cuando exista evidencia.\n"
        "- No mezclar con garantias tecnicas del producto.\n"
        "- Priorizar formato escaneable: una garantia por item, sin texto ornamental."
    ),
    "plazos_clave": (
        "- Devolver unicamente hitos clave: apertura, mantenimiento de oferta, entrega/ejecucion, consultas e impugnaciones.\n"
        "- No inferir fechas; usar solo lo textual extraido.\n"
        "- Preferir `bullet_list` con etiquetas breves por hito (ej: 'Apertura: 14/09/2026 10:00 hs')."
    ),
    "criterios_evaluacion": (
        "- Devolver como se pondera precio vs tecnica y si existe puntaje minimo.\n"
        "- Si hay varios factores, usar `bullet_list` o `table` segun comparabilidad.\n"
        "- Mantener redaccion breve (no explicar contexto ya obvio)."
    ),
    "causales_rechazo": (
        "- Esta es la categoria mas critica: listar motivos de rechazo formal que descalifican sin evaluar oferta.\n"
        "- Priorizar claridad y completitud de causales, sin mezclar requisitos no descalificantes.\n"
        "- Usar `bullet_list` con formula breve: 'Rechazo si ...' (ideal <= 16 palabras)."
    ),
    "anexos_obligatorios": (
        "- Devolver solo formularios/anexos que deben completarse y presentarse si o si.\n"
        "- No incluir certificados externos ni documentacion de terceros (eso va en admisibilidad).\n"
        "- Formato recomendado: `bullet_list` con nombre de anexo + accion requerida."
    ),
}

# Categorias que se muestran como respuesta narrativa en la UI. Distinto de
# `CANONICAL_CATEGORY_PROMPT_MAP` (que incluye tambien `identificacion_procedimiento`,
# usada solo para el titulo/subtitulo del analisis, nunca como una tarjeta de
# categoria propia) para no gastar una llamada LLM de sintesis en una narrativa
# que el frontend nunca renderiza.
NARRATIVE_CATEGORIES = tuple(CATEGORY_LABELS)

_USABLE_STATUSES = {"success", "partial", "not_applicable"}


def _normalize_text_for_comparison(text: str) -> str:
    """Normaliza texto para comparación: elimina acentos, espacios múltiples, lowercase."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _dedupe_narrative_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica sources en narrative usando mismo criterio que graph.py:
    mismo document_id + page_number + citation normalizada = misma fuente.
    Mantiene el primer ID encontrado para cada fuente única."""
    seen: dict[tuple[str, int, str], int] = {}
    deduped: list[dict[str, Any]] = []
    id_mapping: dict[int, int] = {}

    for source in sources:
        doc_id = str(source.get("document_id", ""))
        page = int(source.get("page_number", 0) or 0)
        citation = str(source.get("citation", ""))
        normalized_citation = _normalize_text_for_comparison(citation)
        
        key = (doc_id, page, normalized_citation)
        original_id = int(source.get("id", 0))
        
        if key in seen:
            # Ya existe esta fuente, mapear el ID original al ID canónico
            canonical_id = seen[key]
            id_mapping[original_id] = canonical_id
        else:
            # Nueva fuente única
            new_id = len(deduped)
            seen[key] = new_id
            id_mapping[original_id] = new_id
            deduped.append({
                "id": new_id,
                "document_id": doc_id,
                "page_number": page,
                "citation": citation,
            })
    
    return deduped, id_mapping


def _verify_and_repair_narrative_citations(
    narrative: CategoryNarrative,
    items: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> CategoryNarrative:
    """Verifica que cada citation en narrative.sources exista en los
    source_references originales de items. Citations no verificables se marcan
    pero no se eliminan automáticamente — el llamador decide si descartarlas.
    
    También deduplica sources y remapea source_ids en blocks."""
    
    # 1. Construir pool de citations verificables desde items originales
    verified_citations: set[str] = set()
    for item in items:
        refs = item.get("source_references") or []
        for ref in refs:
            citation = str(ref.get("citation", "")).strip()
            if citation and len(citation) >= 25:
                verified_citations.add(_normalize_text_for_comparison(citation))
    
    # 2. Marcar sources en narrative según si son verificables
    sources_with_validation = []
    for source in narrative.sources:
        source_dict = source.model_dump() if hasattr(source, "model_dump") else dict(source)
        citation = str(source_dict.get("citation", "")).strip()
        normalized = _normalize_text_for_comparison(citation)
        
        # Marcar si la citation no está verificada
        is_verified = normalized in verified_citations
        if not is_verified and len(citation) >= 25:
            # Citation no verificable: agregar metadata interna para logging
            logger.warning(
                "narrative_citation_not_grounded",
                correlation_id=correlation_id,
                document_id=source_dict.get("document_id"),
                page=source_dict.get("page_number"),
                citation_preview=citation[:80],
            )
            source_dict["_unverified"] = True
        
        sources_with_validation.append(source_dict)
    
    # 3. Deduplicar sources
    deduped_sources, id_mapping = _dedupe_narrative_sources(sources_with_validation)
    
    # 4. Remapear source_ids en todos los blocks usando el mapping
    def remap_source_ids(block_data: dict[str, Any]) -> dict[str, Any]:
        if "source_ids" in block_data and isinstance(block_data["source_ids"], list):
            block_data["source_ids"] = [
                id_mapping.get(sid, sid) for sid in block_data["source_ids"]
            ]
        if "items" in block_data and isinstance(block_data["items"], list):
            for item in block_data["items"]:
                if isinstance(item, dict):
                    remap_source_ids(item)
        if "rows" in block_data and isinstance(block_data["rows"], list):
            for row in block_data["rows"]:
                if isinstance(row, dict):
                    remap_source_ids(row)
        return block_data
    
    blocks_data = [block.model_dump() if hasattr(block, "model_dump") else dict(block) for block in narrative.blocks]
    blocks_data = [remap_source_ids(block) for block in blocks_data]
    
    # 5. Reconstruir narrative con sources deduplicados y blocks remapeados
    narrative_dict = narrative.model_dump() if hasattr(narrative, "model_dump") else dict(narrative)
    narrative_dict["sources"] = deduped_sources
    narrative_dict["blocks"] = blocks_data
    
    # Log resumen de deduplicación
    original_count = len(sources_with_validation)
    final_count = len(deduped_sources)
    if original_count > final_count:
        logger.info(
            "narrative_sources_deduplicated",
            correlation_id=correlation_id,
            original=original_count,
            deduplicated=final_count,
            removed=original_count - final_count,
        )
    
    return CategoryNarrative.model_validate(narrative_dict)


@lru_cache(maxsize=1)
def _load_response_base_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / RESPONSE_BASE_PROMPT_FILE
    return prompt_path.read_text(encoding="utf-8")


def _serialize_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
) -> tuple[CategoryNarrative, dict[str, int]] | None:
    """Convierte los items ya extraidos de una categoria en una respuesta de
    experto: bloques en lenguaje natural (parrafo/lista/tabla), nunca metadata
    cruda. Devuelve None si no hay contenido util o si la sintesis falla por
    cualquier motivo (LLM, parseo, validacion) — el llamador (grafo) y el
    frontend ya tienen fallback, asi que una categoria nunca se queda sin
    respuesta por un fallo puntual de este paso."""
    if not items or not _has_usable_content(items):
        return None

    try:
        category_label = CATEGORY_LABELS.get(category_key, category_key)
        category_contract = CATEGORY_OUTPUT_CONTRACTS.get(
            category_key,
            "- Priorizar exactitud, concision y separacion estricta por categoria.",
        )
        prompt = (
            _load_response_base_prompt()
            .replace("{items_json}", _serialize_items(items))
            .replace("{category_label}", category_label)
            .replace("{category_output_contract}", category_contract)
        )

        raw, token_usage = extractors_base._call_llm(messages=[("human", prompt)], correlation_id=correlation_id)
        narrative = CategoryNarrative.model_validate(raw)
        
        # Verificar citations contra items originales y deduplicar sources
        narrative = _verify_and_repair_narrative_citations(
            narrative,
            items,
            correlation_id=correlation_id,
        )

        logger.info(
            "synthesis_completed",
            correlation_id=correlation_id,
            category=category_key,
            blocks=len(narrative.blocks),
            sources=len(narrative.sources),
        )
        return narrative, token_usage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "synthesis_failed",
            correlation_id=correlation_id,
            category=category_key,
            error=str(exc),
        )
        return None
