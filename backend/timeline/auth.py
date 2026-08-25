"""
Helpers de autorización para Timeline.

Valida que el usuario tenga permiso para acceder a eventos/deadlines
de un análisis específico.
"""
from fastapi import HTTPException, status

from analysis.cosmos_runtime import _load_analysis_or_none


def validate_analysis_access(analysis_id: str, user_id: str) -> None:
    """
    Valida que el usuario tenga acceso al análisis especificado.
    
    Args:
        analysis_id: ID del análisis
        user_id: ID del usuario actual
        
    Raises:
        HTTPException: 404 si el análisis no existe, 403 si no es el owner
    """
    analysis = _load_analysis_or_none(analysis_id)
    
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
    
    if analysis.get("created_by") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "No tenés permisos para acceder a este análisis"
                }
            },
        )
