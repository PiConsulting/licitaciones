from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tracking.schemas import (
    AnalysisTracking,
    CreateTrackingCommentRequest,
    StartTrackingResponse,
    TrackingComment,
    UpdateTrackingCommentRequest,
    UpdateCategoryStatusRequest,
    UpdateTrackingItemRequest,
)
from tracking.service import (
    complete_tracking,
    create_comment,
    delete_comment,
    get_tracking,
    list_comments,
    start_tracking,
    update_comment,
    update_category_status,
    update_tracking_item_status,
)
from users.service import get_current_user, http_bearer

tracking_router = APIRouter(prefix="/analyses", tags=["tracking"])


def _http_error_from_code(code: str) -> HTTPException:
    mapping: dict[str, tuple[int, str]] = {
        "ANALYSIS_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Análisis no encontrado"),
        "NO_VERSION_YET": (status.HTTP_400_BAD_REQUEST, "El análisis todavía no tiene una versión consultable"),
        "FORBIDDEN": (status.HTTP_403_FORBIDDEN, "No tenés permisos para este análisis"),
        "TRACKING_NOT_AVAILABLE": (status.HTTP_400_BAD_REQUEST, "El seguimiento solo se puede iniciar para análisis finalizados"),
        "TRACKING_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Seguimiento no encontrado para el análisis"),
        "TRACKING_CATEGORY_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Categoría de seguimiento no encontrada"),
        "TRACKING_ITEM_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Ítem de seguimiento no encontrado"),
        "TRACKING_ITEM_REQUIRED": (status.HTTP_400_BAD_REQUEST, "tracking_item_id es obligatorio para comentarios de ítem"),
        "TRACKING_CATEGORY_COMMENT_ONLY": (status.HTTP_400_BAD_REQUEST, "El comentario siempre debe ser general de la categoría."),
        "INVALID_TRACKING_TRANSITION": (status.HTTP_400_BAD_REQUEST, "Transición de estado no permitida"),
        "TRACKING_CATEGORY_CLOSED": (status.HTTP_409_CONFLICT, "La categoría está cerrada. Reabrí la revisión para modificarla."),
        "TRACKING_COMPLETED_READ_ONLY": (status.HTTP_409_CONFLICT, "El seguimiento está finalizado en modo solo lectura."),
        "TRACKING_COMMENT_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Comentario de seguimiento no encontrado"),
        "TRACKING_CONFLICT": (status.HTTP_409_CONFLICT, "El seguimiento cambió en paralelo. Refrescá el estado y reintentá."),
    }
    http_status, message = mapping.get(code, (status.HTTP_400_BAD_REQUEST, "No se pudo procesar la solicitud de seguimiento"))
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


@tracking_router.post("/{analysis_id}/tracking/start", response_model=StartTrackingResponse)
async def start_analysis_tracking(analysis_id: str, credentials=Depends(http_bearer)) -> StartTrackingResponse:
    current_user = get_current_user(credentials, None)
    try:
        tracking = start_tracking(analysis_id, current_user.id)
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return StartTrackingResponse(tracking=AnalysisTracking(**tracking))


@tracking_router.get("/{analysis_id}/tracking", response_model=AnalysisTracking | None)
async def get_analysis_tracking(analysis_id: str, credentials=Depends(http_bearer)) -> AnalysisTracking | None:
    current_user = get_current_user(credentials, None)
    try:
        tracking = get_tracking(analysis_id, current_user.id)
    except (ValueError, PermissionError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    if tracking is None:
        return None
    return AnalysisTracking(**tracking)


@tracking_router.post("/{analysis_id}/tracking/complete", response_model=AnalysisTracking)
async def complete_analysis_tracking(analysis_id: str, credentials=Depends(http_bearer)) -> AnalysisTracking:
    current_user = get_current_user(credentials, None)
    try:
        tracking = complete_tracking(analysis_id, current_user.id, completed_by_name=current_user.name)
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return AnalysisTracking(**tracking)


@tracking_router.patch("/{analysis_id}/tracking/categories/{category_key}/status", response_model=AnalysisTracking)
async def patch_tracking_category_status(
    analysis_id: str,
    category_key: str,
    payload: UpdateCategoryStatusRequest,
    credentials=Depends(http_bearer),
) -> AnalysisTracking:
    current_user = get_current_user(credentials, None)
    try:
        tracking = update_category_status(analysis_id, current_user.id, category_key, payload.status)
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return AnalysisTracking(**tracking)


@tracking_router.patch("/{analysis_id}/tracking/categories/{category_key}/items/{tracking_item_id}", response_model=AnalysisTracking)
async def patch_tracking_item_status(
    analysis_id: str,
    category_key: str,
    tracking_item_id: str,
    payload: UpdateTrackingItemRequest,
    credentials=Depends(http_bearer),
) -> AnalysisTracking:
    current_user = get_current_user(credentials, None)
    try:
        tracking = update_tracking_item_status(
            analysis_id,
            current_user.id,
            category_key,
            tracking_item_id,
            payload.status,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return AnalysisTracking(**tracking)


@tracking_router.get("/{analysis_id}/tracking/categories/{category_key}/comments", response_model=list[TrackingComment])
async def get_tracking_comments(
    analysis_id: str,
    category_key: str,
    scope: str | None = Query(default=None),
    tracking_item_id: str | None = Query(default=None),
    credentials=Depends(http_bearer),
) -> list[TrackingComment]:
    current_user = get_current_user(credentials, None)
    try:
        comments = list_comments(
            analysis_id,
            current_user.id,
            category_key,
            scope=scope,
            tracking_item_id=tracking_item_id,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return [TrackingComment(**item) for item in comments]


@tracking_router.post("/{analysis_id}/tracking/categories/{category_key}/comments", response_model=TrackingComment)
async def post_tracking_comment(
    analysis_id: str,
    category_key: str,
    payload: CreateTrackingCommentRequest,
    credentials=Depends(http_bearer),
) -> TrackingComment:
    current_user = get_current_user(credentials, None)
    try:
        comment = create_comment(
            analysis_id,
            current_user.id,
            category_key,
            scope=payload.scope,
            content=payload.content,
            tracking_item_id=payload.tracking_item_id,
            created_by_name=current_user.name,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return TrackingComment(**comment)


@tracking_router.patch("/{analysis_id}/tracking/categories/{category_key}/comments/{comment_id}", response_model=TrackingComment)
async def patch_tracking_comment(
    analysis_id: str,
    category_key: str,
    comment_id: str,
    payload: UpdateTrackingCommentRequest,
    credentials=Depends(http_bearer),
) -> TrackingComment:
    current_user = get_current_user(credentials, None)
    try:
        comment = update_comment(
            analysis_id,
            current_user.id,
            category_key,
            comment_id,
            content=payload.content,
            edited_by_name=current_user.name,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
    return TrackingComment(**comment)


@tracking_router.delete("/{analysis_id}/tracking/categories/{category_key}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tracking_comment(
    analysis_id: str,
    category_key: str,
    comment_id: str,
    credentials=Depends(http_bearer),
) -> None:
    current_user = get_current_user(credentials, None)
    try:
        delete_comment(analysis_id, current_user.id, category_key, comment_id)
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error_from_code(str(exc)) from exc
