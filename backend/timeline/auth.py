"""
Helpers de autorización para Timeline.

Valida que el usuario tenga permiso para acceder a eventos/deadlines
de un análisis específico.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from analysis.models import Analysis


def validate_analysis_access(db: Session, analysis_id: str, user_id: str) -> None:
    """
    Valida que el usuario tenga acceso al análisis especificado.

    Args:
        db: Sesión de SQLAlchemy
        analysis_id: ID del análisis
        user_id: ID del usuario actual

    Raises:
        HTTPException: 404 si el análisis no existe, 403 si no es el owner
    """
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
        .first()
    )

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ANALYSIS_NOT_FOUND",
                    "message": "Análisis no encontrado"
                }
            },
        )

    if analysis.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "No tenés permisos para acceder a este análisis"
                }
            },
        )
