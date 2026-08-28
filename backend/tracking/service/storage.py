"""Lectura/escritura de tracking contra PostgreSQL, con control de
concurrencia optimista real (antes ETag de Cosmos): un `UPDATE ... WHERE
updated_at = :expected` que afecta 0 filas es el equivalente exacto del
`CosmosAccessConditionFailedError` de antes -- mismo criterio (AC2/AC3).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from analysis.models import Analysis, AnalysisVersion
from tracking.models import Tracking


def _load_analysis_or_raise(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
        .first()
    )
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.created_by != user_id:
        raise PermissionError("FORBIDDEN")
    return analysis


def _load_latest_version(db: Session, analysis_id: str) -> AnalysisVersion:
    version = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.analysis_id == analysis_id)
        .order_by(AnalysisVersion.version_number.desc())
        .first()
    )
    if version is None:
        raise ValueError("NO_VERSION_YET")
    return version


def _read_tracking_or_none(db: Session, analysis_id: str, version_id: str) -> Tracking | None:
    return (
        db.query(Tracking)
        .filter(Tracking.analysis_id == analysis_id, Tracking.version_id == version_id)
        .first()
    )


def _apply_tracking_cas_update(
    db: Session, tracking_id: str, expected_updated_at: datetime, new_updated_at: datetime | None = None
) -> datetime:
    """Confirma la transacción sólo si `tracking.updated_at` sigue siendo
    `expected_updated_at` -- cualquier otra escritura concurrente (de
    cualquier parte del árbol: la categoría, un item, o el tracking mismo)
    ya la habrá cambiado, y esta llamada afecta 0 filas -> TRACKING_CONFLICT.

    Se llama DESPUÉS de mutar los objetos ORM relevantes (categoría/item) en
    la misma sesión -- `db.flush()` empuja esos cambios a la transacción
    (sin confirmarla), y este UPDATE + commit los hace definitivos junto con
    el nuevo `updated_at`. Si la condición no matchea, se hace rollback:
    todo lo flusheado en esta transacción se descarta también.
    """
    new_updated_at = new_updated_at or datetime.now(UTC)
    db.flush()
    result = db.execute(
        update(Tracking)
        .where(Tracking.id == tracking_id, Tracking.updated_at == expected_updated_at)
        .values(updated_at=new_updated_at)
    )
    if result.rowcount == 0:
        db.rollback()
        raise RuntimeError("TRACKING_CONFLICT")
    db.commit()
    return new_updated_at
