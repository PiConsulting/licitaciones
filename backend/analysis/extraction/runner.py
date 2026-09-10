from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from analysis.extraction.engine.prompts import validate_prompt_inventory
from analysis.extraction.graph import graph, graph_phase1, graph_phase2
from analysis.extraction.state import GraphState
from analysis.models import Analysis, AnalysisVersion, CurrentStage
from analysis.progress import build_stage_progress, update_stage_and_progress
from documents.models import Document
from infra.config import get_settings
from timeline.materializer import materialize_timeline_from_extraction

logger = structlog.get_logger(__name__)
_PROMPT_COST_PER_1K = 0.00015
_COMPLETION_COST_PER_1K = 0.0006
_SETUP_CACHE_KEY = "setup_cache"

# FIX (2026-09-03): garantias, plazos_clave/plazos, requisitos_admisibilidad
# y riesgos se promueven a fase 1 -- preview_criterios ahora proyecta 5 de
# sus 10 items desde los resultados de estas 4 categorias (ver
# `analysis/extraction/extractors/preview_criterios.py` y
# `analysis/extraction/graph/nodes.py`), así que necesitan haber corrido (y
# haber quedado persistidas) ya en fase 1, no en fase 2. "calidad_por_categoria"
# se mueve/agrega acá también -- antes solo vivía en fase 2 y el merge de
# fase 2 con fase 1 solo la traía si YA existía en la versión (ver
# `extract_categories_phase2` más abajo); si no se persiste desde fase 1, las
# entradas de calidad de estas 4 categorías se pierden.
_PHASE1_EXTRACTED_KEYS = {
    "preview_criterios",
    "preview_criterios_extraction_status",
    "preview_criterios_narrative",
    "preview_criterios_confidence",
    "objeto_alcance",
    "objeto_alcance_extraction_status",
    "objeto_alcance_narrative",
    "objeto_alcance_confidence",
    "identificacion_procedimiento",
    "identificacion_procedimiento_extraction_status",
    "identificacion_procedimiento_narrative",
    "datos_procedimiento",
    "datos_procedimiento_extraction_status",
    "datos_procedimiento_confidence",
    "calidad_por_categoria",
    "requisitos_admisibilidad",
    "requisitos_admisibilidad_extraction_status",
    "requisitos_admisibilidad_narrative",
    "requisitos_admisibilidad_confidence",
    "plazos_clave",
    "plazos_clave_extraction_status",
    "plazos_clave_narrative",
    "plazos_clave_confidence",
    "plazos",
    "plazos_extraction_status",
    "garantias",
    "garantias_extraction_status",
    "garantias_narrative",
    "garantias_confidence",
    "riesgos",
    "riesgos_extraction_status",
    "riesgos_narrative",
    "riesgos_confidence",
}

_PHASE2_EXTRACTED_KEYS = {
    "calidad_por_categoria",
    "causales_rechazo",
    "causales_rechazo_extraction_status",
    "causales_rechazo_narrative",
    "causales_extraction_status",
    "causales_rechazo_confidence",
    "anexos_obligatorios",
    "anexos_obligatorios_extraction_status",
    "anexos_obligatorios_narrative",
    "anexos_obligatorios_confidence",
    "criterios_evaluacion",
    "criterios_evaluacion_extraction_status",
    "criterios_evaluacion_narrative",
    "criterios_evaluacion_confidence",
    "eventos_temporales",
    "eventos_temporales_extraction_status",
    "plazos_relativos",
    "plazos_relativos_extraction_status",
}


def _merge_conflicts(
    existing_conflicts: list[dict] | None, incoming_conflicts: list[dict] | None
) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for conflict in (existing_conflicts or []) + (incoming_conflicts or []):
        fingerprint = json.dumps(conflict, sort_keys=True, ensure_ascii=True, default=str)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        merged.append(conflict)

    return merged


def _compute_cost(metadata: dict) -> dict:
    usage_by_category = metadata.get("token_usage", {}) if metadata else {}
    prompt_tokens = sum(int(item.get("prompt_tokens", 0)) for item in usage_by_category.values())
    completion_tokens = sum(
        int(item.get("completion_tokens", 0)) for item in usage_by_category.values()
    )
    total_tokens = sum(int(item.get("total_tokens", 0)) for item in usage_by_category.values())

    total_cost = ((prompt_tokens / 1000) * _PROMPT_COST_PER_1K) + (
        (completion_tokens / 1000) * _COMPLETION_COST_PER_1K
    )
    # Instrumentación (Paso 0.1, plan rag-plan-latencia-2026-09-09): nº total
    # de llamadas al LLM (extracción map-reduce + síntesis) y wall-time por
    # categoría, para medir el efecto de cada cambio de paralelización.
    llm_calls_total = sum(int(item.get("llm_calls", 0)) for item in usage_by_category.values())
    wall_time_by_category = {
        name: item["wall_time_seconds"]
        for name, item in usage_by_category.items()
        if isinstance(item, dict) and "wall_time_seconds" in item
    }
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 8),
        "llm_calls_total": llm_calls_total,
        "wall_time_by_category": wall_time_by_category,
    }


def _build_initial_state(
    db: Session,
    analysis: Analysis,
    max_concurrency: int,
    *,
    setup_cache: dict | None = None,
) -> GraphState:
    state: GraphState = {
        "analysis_id": analysis.id,
        "correlation_id": analysis.correlation_id,
        "created_by": analysis.created_by,
        "max_concurrency": max_concurrency,
        "extraction_metadata": {},
        "db_session": db,
    }
    if setup_cache:
        state.update(setup_cache)
    return state


def _get_analysis_document_ids(db: Session, analysis_id: str) -> list[str]:
    rows = (
        db.query(Document.id)
        .filter(Document.analysis_id == analysis_id, Document.deleted_at.is_(None))
        .order_by(Document.uploaded_at.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def _build_setup_cache_from_result(result: GraphState, analysis_id: str) -> dict | None:
    mapping = result.get("document_id_to_blob_path")
    labels = result.get("document_labels")
    candidates = result.get("global_candidates")

    if not isinstance(mapping, dict) or not isinstance(labels, dict) or not isinstance(candidates, list):
        return None

    return {
        "analysis_id": analysis_id,
        "document_ids": sorted(str(doc_id) for doc_id in mapping.keys()),
        "document_id_to_blob_path": mapping,
        "document_labels": labels,
        "global_candidates": candidates,
        "cached_at": datetime.now(UTC).isoformat(),
    }


def _load_setup_cache_for_initial_state(db: Session, analysis: Analysis) -> dict | None:
    metadata = analysis.extraction_metadata or {}
    cache = metadata.get(_SETUP_CACHE_KEY)
    if not isinstance(cache, dict):
        return None

    if str(cache.get("analysis_id")) != str(analysis.id):
        return None

    cached_doc_ids = cache.get("document_ids")
    if not isinstance(cached_doc_ids, list):
        return None

    current_doc_ids = sorted(_get_analysis_document_ids(db, analysis.id))
    normalized_cached_doc_ids = sorted(str(item) for item in cached_doc_ids)
    if current_doc_ids != normalized_cached_doc_ids:
        logger.info(
            "setup_cache_invalidated_document_mismatch",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis.id,
            current_documents=len(current_doc_ids),
            cached_documents=len(normalized_cached_doc_ids),
        )
        return None

    mapping = cache.get("document_id_to_blob_path")
    labels = cache.get("document_labels")
    candidates = cache.get("global_candidates")
    if not isinstance(mapping, dict) or not isinstance(labels, dict) or not isinstance(candidates, list):
        return None

    logger.info(
        "setup_cache_available",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        documents=len(mapping),
        candidates=len(candidates),
    )
    return {
        "document_id_to_blob_path": mapping,
        "document_labels": labels,
        "global_candidates": candidates,
    }


def _set_completed_stage(db: Session, analysis: Analysis, metadata: dict, *, status: str) -> None:
    analysis.extraction_metadata = {
        **metadata,
        "stage_progress": build_stage_progress(CurrentStage.COMPLETED),
    }
    analysis.status = status
    analysis.current_stage = CurrentStage.COMPLETED.value
    analysis.progress_percentage = 100
    analysis.error_message = None
    analysis.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(analysis)


def extract_categories(db: Session, analysis: Analysis) -> GraphState:
    settings = get_settings()
    max_concurrency = int(settings.extraction_max_concurrency or 4)
    validate_prompt_inventory()

    initial_state = _build_initial_state(db, analysis, max_concurrency)

    logger.info(
        "category_extraction_started",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        max_concurrency=max_concurrency,
    )
    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.ANALYZING,
        progress_increment=45,
        stage_progress=build_stage_progress(CurrentStage.ANALYZING, done=8, total=8),
        status="processing",
    )

    _invoke_started = time.monotonic()
    result = graph.invoke(initial_state, config={"max_concurrency": max_concurrency})

    extracted_data = result.get("extracted_data", {})
    timeline_eventos = extracted_data.get("eventos_temporales", result.get("eventos_temporales", []))
    timeline_plazos = extracted_data.get("plazos_relativos", result.get("plazos_relativos", []))
    conflicts = result.get("conflicts", [])
    metadata = result.get("extraction_metadata", {})
    metadata["wall_time_seconds"] = round(time.monotonic() - _invoke_started, 2)
    metadata["cost"] = _compute_cost(metadata)

    current_version_number = (
        db.query(func.max(AnalysisVersion.version_number))
        .filter(AnalysisVersion.analysis_id == analysis.id)
        .scalar()
    ) or 0
    new_version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=int(current_version_number) + 1,
        extracted_data=extracted_data,
        conflicts=conflicts,
        created_by=analysis.created_by,
    )
    db.add(new_version)
    db.flush()

    try:
        materialize_result = materialize_timeline_from_extraction(
            db,
            analysis_id=analysis.id,
            created_by=analysis.created_by,
            eventos_temporales=timeline_eventos,
            plazos_relativos=timeline_plazos,
        )
        logger.info(
            "timeline_materialized",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis.id,
            events_created=materialize_result.events_created,
            deadlines_created=materialize_result.deadlines_created,
            skipped_count=len(materialize_result.skipped),
        )
    except Exception:
        # No debe bloquear que el análisis se marque como analizado -- el
        # Timeline queda vacío para este análisis (como hoy), pero el resto
        # de los resultados de la extracción se guardan igual.
        logger.exception(
            "timeline_materialization_failed",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis.id,
        )

    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.CONSOLIDATING,
        progress_increment=15,
        stage_progress=build_stage_progress(CurrentStage.CONSOLIDATING),
        status="processing",
    )

    analysis.current_version_id = new_version.id
    _set_completed_stage(db, analysis, metadata, status="analyzed")

    logger.info(
        "category_extraction_completed",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        version_id=new_version.id,
        conflicts_count=len(conflicts),
        total_tokens=metadata["cost"]["total_tokens"],
        estimated_cost_usd=metadata["cost"]["estimated_cost_usd"],
        llm_calls_total=metadata["cost"].get("llm_calls_total"),
        wall_time_seconds=metadata.get("wall_time_seconds"),
    )
    return result


def extract_categories_phase1(
    db: Session,
    analysis: Analysis,
    *,
    total_nodes: int,
) -> GraphState:
    settings = get_settings()
    max_concurrency = int(settings.extraction_max_concurrency or 4)
    validate_prompt_inventory()

    initial_state = _build_initial_state(db, analysis, max_concurrency)
    logger.info(
        "category_extraction_phase1_started",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        max_concurrency=max_concurrency,
        total_nodes=total_nodes,
    )

    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.ANALYZING,
        progress_increment=45,
        stage_progress=build_stage_progress(
            CurrentStage.ANALYZING,
            done=0,
            total=total_nodes,
            analyzing_label="preview",
        ),
        status="processing",
    )

    _invoke_started = time.monotonic()
    result = graph_phase1.invoke(initial_state, config={"max_concurrency": max_concurrency})
    extracted_data = result.get("extracted_data", {})
    phase1_extracted_data = {k: v for k, v in extracted_data.items() if k in _PHASE1_EXTRACTED_KEYS}
    metadata = result.get("extraction_metadata", {})
    metadata["wall_time_seconds"] = round(time.monotonic() - _invoke_started, 2)
    setup_cache = _build_setup_cache_from_result(result, analysis.id)
    if setup_cache is not None:
        metadata[_SETUP_CACHE_KEY] = setup_cache
    metadata["cost"] = _compute_cost(metadata)

    current_version_number = (
        db.query(func.max(AnalysisVersion.version_number))
        .filter(AnalysisVersion.analysis_id == analysis.id)
        .scalar()
    ) or 0
    new_version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=int(current_version_number) + 1,
        extracted_data=phase1_extracted_data,
        conflicts=result.get("conflicts", []),
        created_by=analysis.created_by,
    )
    db.add(new_version)
    db.flush()

    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.CONSOLIDATING,
        progress_increment=15,
        stage_progress=build_stage_progress(CurrentStage.CONSOLIDATING),
        status="processing",
    )

    analysis.current_version_id = new_version.id
    _set_completed_stage(db, analysis, metadata, status="en_revision")

    logger.info(
        "category_extraction_phase1_completed",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        version_id=new_version.id,
        llm_calls_total=metadata["cost"].get("llm_calls_total"),
        wall_time_seconds=metadata.get("wall_time_seconds"),
    )
    return result


def extract_categories_phase2(
    db: Session,
    analysis: Analysis,
    *,
    total_nodes: int,
) -> GraphState:
    settings = get_settings()
    max_concurrency = int(settings.extraction_max_concurrency or 4)
    validate_prompt_inventory()

    setup_cache = _load_setup_cache_for_initial_state(db, analysis)
    initial_state = _build_initial_state(
        db,
        analysis,
        max_concurrency,
        setup_cache=setup_cache,
    )
    logger.info(
        "category_extraction_phase2_started",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        max_concurrency=max_concurrency,
        total_nodes=total_nodes,
    )

    current_version = None
    if analysis.current_version_id:
        current_version = (
            db.query(AnalysisVersion)
            .filter(
                AnalysisVersion.id == analysis.current_version_id,
                AnalysisVersion.analysis_id == analysis.id,
            )
            .first()
        )
    if current_version is None:
        raise RuntimeError("No se encontró la AnalysisVersion de fase 1 para completar fase 2")

    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.ANALYZING,
        progress_increment=45,
        stage_progress=build_stage_progress(
            CurrentStage.ANALYZING,
            done=0,
            total=total_nodes,
            analyzing_label="categorias",
        ),
        status="processing",
    )

    _invoke_started = time.monotonic()
    result = graph_phase2.invoke(initial_state, config={"max_concurrency": max_concurrency})
    extracted_data = result.get("extracted_data", {})
    timeline_eventos = extracted_data.get("eventos_temporales", result.get("eventos_temporales", []))
    timeline_plazos = extracted_data.get("plazos_relativos", result.get("plazos_relativos", []))
    phase2_extracted_data = {k: v for k, v in extracted_data.items() if k in _PHASE2_EXTRACTED_KEYS}
    metadata = result.get("extraction_metadata", {})
    metadata["wall_time_seconds"] = round(time.monotonic() - _invoke_started, 2)
    metadata["cost"] = _compute_cost(metadata)

    # Decisión de diseño (Epic P1, 2026-09-02): fase 2 NO crea versión nueva.
    # Solo completa la primera corrida y actualiza in-place la version_number=1.
    merged_extracted_data = dict(current_version.extracted_data or {})
    calidad_existente = merged_extracted_data.get("calidad_por_categoria")
    calidad_nueva = phase2_extracted_data.get("calidad_por_categoria")
    if isinstance(calidad_existente, dict) and isinstance(calidad_nueva, dict):
        phase2_extracted_data["calidad_por_categoria"] = {
            **calidad_existente,
            **calidad_nueva,
        }
    merged_extracted_data.update(phase2_extracted_data)
    current_version.extracted_data = merged_extracted_data
    current_version.conflicts = _merge_conflicts(
        current_version.conflicts,
        result.get("conflicts", []),
    )
    db.flush()

    try:
        materialize_result = materialize_timeline_from_extraction(
            db,
            analysis_id=analysis.id,
            created_by=analysis.created_by,
            eventos_temporales=timeline_eventos,
            plazos_relativos=timeline_plazos,
        )
        logger.info(
            "timeline_materialized_phase2",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis.id,
            events_created=materialize_result.events_created,
            deadlines_created=materialize_result.deadlines_created,
            skipped_count=len(materialize_result.skipped),
        )
    except Exception:
        logger.exception(
            "timeline_materialization_phase2_failed",
            correlation_id=analysis.correlation_id,
            analysis_id=analysis.id,
        )

    update_stage_and_progress(
        db,
        analysis.id,
        CurrentStage.CONSOLIDATING,
        progress_increment=15,
        stage_progress=build_stage_progress(CurrentStage.CONSOLIDATING),
        status="processing",
    )

    analysis.extraction_metadata = {
        **(analysis.extraction_metadata or {}),
        **metadata,
    }
    _set_completed_stage(db, analysis, analysis.extraction_metadata or {}, status="analyzed")

    logger.info(
        "category_extraction_phase2_completed",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        version_id=current_version.id,
        llm_calls_total=metadata["cost"].get("llm_calls_total"),
        wall_time_seconds=metadata.get("wall_time_seconds"),
    )
    return result
