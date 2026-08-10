from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from analysis.models import Analysis, CurrentStage

STAGE_PROGRESS_MAP: dict[CurrentStage, int] = {
    CurrentStage.QUEUED: 0,
    CurrentStage.EXTRACTING_TEXT: 10,
    CurrentStage.INDEXING: 20,
    CurrentStage.ANALYZING: 30,
    CurrentStage.CONSOLIDATING: 80,
    CurrentStage.COMPLETED: 100,
}

TERMINAL_STATUSES = {"analyzed", "error", "cancelled"}


def calculate_timeout_minutes(total_pages: int) -> int:
    if total_pages <= 50:
        return 8
    if total_pages <= 100:
        return 12
    if total_pages <= 200:
        return 18
    return 25


def set_timeout_timestamps(analysis: Analysis, total_pages: int, *, now: datetime | None = None) -> None:
    reference_now = now or datetime.now(UTC)
    timeout_minutes = calculate_timeout_minutes(total_pages)
    analysis.started_at = reference_now
    analysis.timeout_at = reference_now + timedelta(minutes=timeout_minutes)
    analysis.timeout_warning_at = analysis.timeout_at - timedelta(minutes=2)


def build_stage_progress(stage: CurrentStage, *, done: int | None = None, total: int | None = None) -> str:
    if stage == CurrentStage.QUEUED:
        return "En cola"
    if stage == CurrentStage.EXTRACTING_TEXT and done is not None and total is not None:
        return f"Extrayendo texto ({done} de {total} documentos)"
    if stage == CurrentStage.INDEXING:
        return "Preparando para análisis"
    if stage == CurrentStage.ANALYZING and done is not None and total is not None:
        return f"Analizando categorias ({done} de {total})"
    if stage == CurrentStage.CONSOLIDATING:
        return "Consolidando"
    return "Analizado"


def update_stage_and_progress(
    db: Session,
    analysis_id: str,
    stage: CurrentStage,
    *,
    progress_increment: int = 0,
    stage_progress: str | None = None,
    status: str | None = None,
) -> Analysis | None:
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    if analysis is None:
        return None

    base_progress = STAGE_PROGRESS_MAP[stage]
    analysis.current_stage = stage.value
    if status is not None:
        analysis.status = status
    analysis.progress_percentage = min(100, max(analysis.progress_percentage or 0, base_progress + progress_increment))
    if stage_progress:
        analysis.extraction_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": stage_progress,
        }
    analysis.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(analysis)
    return analysis


def mark_timeout_error(analysis: Analysis, timeout_minutes: int) -> None:
    analysis.status = "error"
    analysis.current_stage = CurrentStage.COMPLETED.value
    analysis.progress_percentage = min(analysis.progress_percentage or 0, 95)
    analysis.error_message = (
        f"El analisis supero el tiempo maximo ({timeout_minutes} minutos) y se detuvo. "
        "Podes volver a cargar el pliego e intentarlo nuevamente"
    )
