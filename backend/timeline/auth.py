"""
Helpers de autorización para Timeline.

Valida que el usuario tenga permiso para acceder a eventos/deadlines
de un análisis específico.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from users.access import get_visible_analysis


def validate_analysis_access(db: Session, analysis_id: str, user_id: str) -> None:
    if get_visible_analysis(db, analysis_id, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ANALYSIS_NOT_FOUND",
                    "message": "Análisis no encontrado",
                }
            },
        )
