from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from analysis.extraction.engine.prompts import validate_prompt_inventory
from analysis.extraction.graph import graph
from analysis.extraction.state import GraphState
from analysis.models import Analysis, AnalysisVersion, CurrentStage
from analysis.progress import build_stage_progress, update_stage_and_progress
from infra.config import get_settings
from timeline.materializer import materialize_timeline_from_extraction

logger = structlog.get_logger(__name__)
_PROMPT_COST_PER_1K = 0.00015
_COMPLETION_COST_PER_1K = 0.0006


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
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 8),
    }


def extract_categories(db: Session, analysis: Analysis) -> GraphState:
    settings = get_settings()
    max_concurrency = int(settings.extraction_max_concurrency or 4)
    validate_prompt_inventory()

    initial_state: GraphState = {
        "analysis_id": analysis.id,
        "correlation_id": analysis.correlation_id,
        "created_by": analysis.created_by,
        "max_concurrency": max_concurrency,
        "extraction_metadata": {},
        "db_session": db,
    }

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

    result = graph.invoke(initial_state, config={"max_concurrency": max_concurrency})

    extracted_data = result.get("extracted_data", {})
    conflicts = result.get("conflicts", [])
    metadata = result.get("extraction_metadata", {})
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
            eventos_temporales=result.get("eventos_temporales", []),
            plazos_relativos=result.get("plazos_relativos", []),
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
    analysis.extraction_metadata = metadata
    analysis.status = "analyzed"
    analysis.current_stage = CurrentStage.COMPLETED.value
    analysis.progress_percentage = 100
    analysis.error_message = None
    analysis.extraction_metadata = {
        **metadata,
        "stage_progress": build_stage_progress(CurrentStage.COMPLETED),
    }
    analysis.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(analysis)

    logger.info(
        "category_extraction_completed",
        correlation_id=analysis.correlation_id,
        analysis_id=analysis.id,
        version_id=new_version.id,
        conflicts_count=len(conflicts),
        total_tokens=metadata["cost"]["total_tokens"],
        estimated_cost_usd=metadata["cost"]["estimated_cost_usd"],
    )
    return result
