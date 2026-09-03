"""Entrypoint de sintesis: arma el prompt por categoria, llama al LLM y resuelve la narrativa final con sus fuentes ya verificadas."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.engine import base as extraction_engine
from analysis.extraction.schemas import CategoryNarrative, RawCategoryNarrative
from analysis.extraction.synthesis.prompt_and_serialization import (
    _conflict_block,
    _empty_category_narrative,
    _has_usable_content,
    _load_response_base_prompt,
    _serialize_items,
)
from analysis.extraction.synthesis.source_resolution import _resolve_narrative_sources

try:
    from analysis.extraction.highlight import compute_highlights_for_sources

    HIGHLIGHT_AVAILABLE = True
except ImportError:
    HIGHLIGHT_AVAILABLE = False
    compute_highlights_for_sources = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

CATEGORY_LABELS = {
    "preview_criterios": "Preview Criterios",
    "objeto_alcance": "Objeto y Alcance",
    "requisitos_admisibilidad": "Requisitos de Admisibilidad",
    "garantias": "Garantías",
    "plazos_clave": "Plazos Clave",
    "criterios_evaluacion": "Criterios de Evaluación",
    "causales_rechazo": "Causales de Rechazo",
    "anexos_obligatorios": "Anexos Obligatorios",
    "riesgos": "Riesgos",
}
CATEGORY_OUTPUT_CONTRACTS = {
    "preview_criterios": (
        "- Sintetizar criterios preliminares clave para decisión temprana de oportunidad.\n"
        "- Emitir SIEMPRE una lista con exactamente un bullet por cada item recibido.\n"
        "- Cada bullet debe empezar con el nombre legible del criterio y seguir con una respuesta breve en lenguaje natural.\n"
        "- Si el item tiene extraction_status='not_found' o 'failed', escribir explícitamente que no se encontró información para ese criterio, sin omitirlo.\n"
        "- Usar redacción breve y accionable por criterio, sin inventar datos no citados.\n"
        "- Priorizar texto verificable respaldado por evidencia del pliego cuando exista."
    ),
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
        "- Usar `bullet_list`, un item por plazo distinto.\n"
        "- Cada bullet debe usar el `texto_original` del item, que ya contiene descripcion\n"
        "  completa del plazo con contexto (QUE plazo es, CUANDO se cuenta, QUIEN lo ejecuta).\n"
        "- FIX (2026-08-21): El campo `tipo` ahora es opcional. NO usar 'tipo' para etiquetar\n"
        "  bullets. Escribir el texto_original directamente, sin prefijos artificiales.\n"
        "- Si el hito tiene fecha/hora limpia y sin condicion (ej: apertura, presentacion),\n"
        "  podés reformular brevemente: 'Apertura: 14/09/2026 10:00 hs'.\n"
        "- Si el plazo depende de una condicion o disparador (ej: 'a partir de la recepcion\n"
        "  provisoria de cada hito...'), expresar la oracion completa y bien formada, sin\n"
        "  perder a que se refiere el plazo ni la condicion que lo activa.\n"
        "- Si dos bullets terminarian describiendo el mismo plazo con fragmentos distintos\n"
        "  de la misma oracion (la condicion en uno, la duracion en otro), consolidalos\n"
        "  en un solo bullet.\n"
        "- NUNCA empezar un bullet con 'Otro:' ni usar clasificaciones tecnicas internas\n"
        "  como etiquetas. El texto_original ya es descriptivo y auto-contenido.\n"
        "  Ejemplo correcto:\n"
        "  'La Provincia dispone de un plazo maximo de 15 dias corridos desde la recepcion\n"
        "  provisoria de cada hito del Plan de Entrega y Servicios para otorgar la F.A.D.'\n"
        "- No inferir fechas; usar solo lo textual extraido."
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
    "riesgos": (
        "- Listar riesgos identificables que puedan afectar la participación o ejecución del contrato.\n"
        "- Incluir consecuencias de incumplimientos (multas, penalizaciones, rescisión).\n"
        "- Usar `bullet_list` con descripción clara y concisa del riesgo.\n"
        "- No duplicar causales de rechazo ni requisitos (van en sus categorías propias)."
    ),
}
NARRATIVE_CATEGORIES = tuple(CATEGORY_LABELS)


def run_synthesis(
    *,
    category_key: str,
    items: list[dict[str, Any]],
    correlation_id: str,
    chunks_by_id: dict[str, dict] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> tuple[CategoryNarrative, dict[str, int]] | None:
    """Convierte los items ya extraidos de una categoria en una respuesta de
    experto: bloques en lenguaje natural (parrafo/lista/tabla), nunca metadata
    cruda. Devuelve None si no hay contenido util o si la sintesis falla por
    cualquier motivo (LLM, parseo, validacion) — el llamador (grafo) y el
    frontend ya tienen fallback, asi que una categoria nunca se queda sin
    respuesta por un fallo puntual de este paso."""
    if not items or not _has_usable_content(items):
        if category_key == "preview_criterios":
            category_label = CATEGORY_LABELS.get(category_key, category_key)
            return _empty_category_narrative(category_label), {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
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
            .replace("{conflicts_block}", _conflict_block(category_key, conflicts))
        )

        raw, token_usage = extraction_engine._call_llm(
            messages=[("human", prompt)], correlation_id=correlation_id
        )
        raw_narrative = RawCategoryNarrative.model_validate(raw)

        narrative = _resolve_narrative_sources(
            raw_narrative,
            items,
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
            keep_empty_for_statuses={"not_found", "failed"} if category_key == "preview_criterios" else None,
        )
        if not narrative.blocks:
            logger.error(
                "synthesis_fell_back_to_empty_narrative_despite_usable_items",
                correlation_id=correlation_id,
                category=category_key,
                items_count=len(items),
                items_with_sources=sum(1 for item in items if item.get("source_references")),
                raw_blocks=len(raw_narrative.blocks),
                raw_evidence=len(raw_narrative.evidence),
                impact="el usuario verá 'No se encontró información' para una categoría que sí tiene datos extraídos",
            )
            narrative = _empty_category_narrative(category_label)

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


def _build_chunks_index_from_search(
    analysis_id: str, correlation_id: str
) -> dict[tuple[str, int], list[dict]]:
    """Construye índice de chunks por (document_id, page_number) desde pgvector."""
    try:
        from infra.ports.pgvector_search import fetch_all_analysis_chunks

        all_chunks, truncated = fetch_all_analysis_chunks(analysis_id)
        chunks_by_doc_page: dict[tuple[str, int], list[dict]] = {}
        for chunk in all_chunks:
            doc_id = chunk.get("document_id")
            page = chunk.get("page_number")
            if not doc_id or not page:
                continue
            key = (str(doc_id), int(page))
            if key not in chunks_by_doc_page:
                chunks_by_doc_page[key] = []
            chunks_by_doc_page[key].append(chunk)

        logger.info(
            "chunks_index_built",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            total_chunks=len(all_chunks),
            unique_pages=len(chunks_by_doc_page),
            truncated=truncated,
        )

        return chunks_by_doc_page

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chunks_index_build_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            error=str(exc),
            message="Highlight no disponible - no se pudo construir índice de chunks",
        )
        return {}


def enrich_narrative_with_highlights(
    narrative: CategoryNarrative,
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
    *,
    category_key: str | None = None,
    analysis_id: str | None = None,
    chunks_by_doc_page: dict[tuple[str, int], list[dict]] | None = None,
) -> CategoryNarrative:
    """Enriquece una CategoryNarrative con coordenadas de highlight pre-computadas."""
    if not HIGHLIGHT_AVAILABLE:
        logger.info(
            "highlight_skipped_not_available",
            correlation_id=correlation_id,
            message="PyMuPDF no instalado - highlights no disponibles",
        )
        return narrative

    if not narrative.sources:
        return narrative

    if chunks_by_doc_page is None:
        if analysis_id:
            logger.info(
                "highlight_building_own_chunks_index",
                correlation_id=correlation_id,
                category_key=category_key,
                reason="no se recibió chunks_by_doc_page; se construye localmente",
            )
            chunks_by_doc_page = _build_chunks_index_from_search(analysis_id, correlation_id)
        else:
            chunks_by_doc_page = {}
            logger.warning(
                "highlight_skipped_no_analysis_id",
                correlation_id=correlation_id,
                message="analysis_id no disponible - highlights no se calcularán",
            )

    try:
        sources_data = [source.model_dump() for source in narrative.sources]
        enriched_sources_data = compute_highlights_for_sources(
            sources=sources_data,
            document_id_to_blob_path=document_id_to_blob_path,
            correlation_id=correlation_id,
            category_key=category_key,
            chunks_by_doc_page=chunks_by_doc_page,
        )
        narrative_data = narrative.model_dump()
        narrative_data["sources"] = enriched_sources_data

        return CategoryNarrative.model_validate(narrative_data)

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "highlight_enrichment_failed",
            correlation_id=correlation_id,
            error=str(exc),
            message="Highlights no disponibles - narrative devuelta sin modificar",
        )
        return narrative
