"""Logica compartida de cancelacion, usada tanto por el endpoint de cancelar
(via lifecycle.request_cancellation) como por los checkpoints del pipeline en
background (indexing.runner.check_cancellation_requested). Vive en un modulo
propio para que ninguno de los dos tenga que importar al otro."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from analysis.models import Analysis, AnalysisVersion, CurrentStage


def revert_or_mark_cancelled(analysis: Analysis, db: Session) -> None:
    """Aplica el efecto de una cancelacion sobre `analysis`.

    Si habia un reanalisis en curso (metadata con `reanalysis_type` +
    `reanalysis_source_status`, escritos por `/reanalyze`), cancelar NO debe
    marcar todo el analisis como "cancelled" ni esconder el boton de
    reanalizar: eso es para cancelar un analisis nuevo (el flujo de la otra
    seccion). En ese caso se descarta el intento y se vuelve al status/version
    previos, como si el reanalisis nunca se hubiera disparado.

    Si no hay reanalisis en curso, se preserva el comportamiento historico:
    marcar el analisis como "cancelled".
    """
    if analysis.status in {"analyzed", "error", "cancelled"}:
        # Terminal: cancelar no hace nada (comportamiento previo).
        return

    metadata = dict(analysis.extraction_metadata or {})
    reanalysis_type = metadata.get("reanalysis_type")
    source_status = metadata.get("reanalysis_source_status")

    if reanalysis_type and source_status:
        source_version_id = metadata.get("reanalysis_source_version_id")
        if (
            source_version_id
            and analysis.current_version_id
            and analysis.current_version_id != source_version_id
        ):
            orphan_id = analysis.current_version_id
            analysis.current_version_id = source_version_id
            db.flush()
            orphan = db.query(AnalysisVersion).filter(AnalysisVersion.id == orphan_id).first()
            if orphan is not None:
                db.delete(orphan)

        analysis.status = source_status
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.error_message = None
        for key in (
            "reanalysis_type",
            "reanalysis_categories",
            "reanalysis_started_at",
            "reanalysis_source_status",
            "reanalysis_source_version_id",
            "stage_progress",
        ):
            metadata.pop(key, None)
        analysis.extraction_metadata = metadata
    else:
        analysis.status = "cancelled"
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.progress_percentage = max(analysis.progress_percentage or 0, 95)
        analysis.error_message = "El analisis fue cancelado por el usuario"

    analysis.updated_at = datetime.now(UTC)
