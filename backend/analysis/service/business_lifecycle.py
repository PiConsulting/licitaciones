from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from analysis.models import (
    Analysis,
    AnalysisPresentation,
    AnalysisResult,
    BusinessStatus,
    BusinessStatusHistory,
)
from analysis.schemas import (
    BusinessStatusHistoryItem,
    BusinessStatusStateResponse,
    PresentationRequest,
    PresentationResponse,
    ReceiptUrlResponse,
    ResultRequest,
    ResultResponse,
)
from analysis.service.business_status import (
    is_valid_business_status_transition,
    update_business_status,
)
from users.models import User

PHASE_ONE_COMPLETED_STATUSES = frozenset({"en_revision", "analyzed", "validated"})
RECEIPT_MAX_BYTES = 10 * 1024 * 1024
RECEIPT_CONTENT_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg", "image/webp"})


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _invalid_transition(current: str | None, target: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": {
                "code": "INVALID_BUSINESS_STATUS_TRANSITION",
                "message": f"No se puede pasar de '{current or 'sin estado'}' a '{target}'",
            }
        },
    )


def _enter_pending_decision(db: Session, analysis: Analysis, user_id: str) -> None:
    update_business_status(
        db,
        analysis=analysis,
        target_status=BusinessStatus.EN_ANALISIS.value,
        user_id=user_id,
    )
    update_business_status(
        db,
        analysis=analysis,
        target_status=BusinessStatus.PENDIENTE_DECISION.value,
        user_id=user_id,
    )


def _decision_target(decision: str | None) -> str | None:
    if decision == "approved":
        return BusinessStatus.EN_REVISION.value
    if decision == "rejected":
        return BusinessStatus.NO_APROBADA.value
    return None


def _move_if_valid(db: Session, analysis: Analysis, target: str | None, user_id: str) -> None:
    if target is None or analysis.business_status == target:
        return
    if is_valid_business_status_transition(analysis.business_status, target):
        update_business_status(db, analysis=analysis, target_status=target, user_id=user_id)


def sync_business_status(db: Session, analysis: Analysis, user_id: str) -> None:
    if analysis.business_status is not None:
        return
    if analysis.status not in PHASE_ONE_COMPLETED_STATUSES:
        return

    _enter_pending_decision(db, analysis, user_id)
    _move_if_valid(db, analysis, _decision_target(analysis.categories_decision), user_id)


def apply_categories_decision(db: Session, analysis: Analysis, decision: str, user_id: str) -> None:
    if analysis.business_status is None:
        _enter_pending_decision(db, analysis, user_id)
    _move_if_valid(db, analysis, _decision_target(decision), user_id)


def save_presentation(
    db: Session, analysis: Analysis, user: User, payload: PresentationRequest
) -> None:
    sync_business_status(db, analysis, user.id)
    current = analysis.business_status
    editable = {BusinessStatus.EN_REVISION.value, BusinessStatus.PRESENTADA.value}
    if current not in editable:
        raise _invalid_transition(current, BusinessStatus.PRESENTADA.value)

    presentation = analysis.presentation
    if presentation is None:
        presentation = AnalysisPresentation(analysis_id=analysis.id, created_by=user.id)
        db.add(presentation)

    presentation.presented_at = payload.presented_at
    presentation.amount = _to_decimal(payload.amount)
    presentation.currency = payload.currency
    presentation.channel = payload.channel
    presentation.offer_number = payload.offer_number
    presentation.notes = payload.notes

    if current == BusinessStatus.EN_REVISION.value:
        update_business_status(
            db,
            analysis=analysis,
            target_status=BusinessStatus.PRESENTADA.value,
            user_id=user.id,
            note=payload.notes,
        )
    else:
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    db.refresh(analysis)


def save_result(db: Session, analysis: Analysis, user: User, payload: ResultRequest) -> None:
    sync_business_status(db, analysis, user.id)
    current = analysis.business_status
    is_first_result = current == BusinessStatus.PRESENTADA.value
    is_edit = current == payload.outcome and analysis.result is not None
    if not is_first_result and not is_edit:
        raise _invalid_transition(current, payload.outcome)

    result = analysis.result
    if result is None:
        result = AnalysisResult(analysis_id=analysis.id, created_by=user.id)
        db.add(result)

    result.outcome = payload.outcome
    result.resulted_at = payload.resulted_at
    result.awarded_amount = _to_decimal(payload.awarded_amount)
    result.loss_reason = payload.loss_reason
    result.winner_name = payload.winner_name
    result.winner_amount = _to_decimal(payload.winner_amount)
    result.notes = payload.notes

    if is_first_result:
        update_business_status(
            db,
            analysis=analysis,
            target_status=payload.outcome,
            user_id=user.id,
            note=payload.notes,
        )
    else:
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    db.refresh(analysis)


def build_business_state(db: Session, analysis: Analysis) -> BusinessStatusStateResponse:
    history_rows: list[BusinessStatusHistory] = list(analysis.business_status_history)
    user_ids = {row.changed_by for row in history_rows if row.changed_by}
    names: dict[str, str] = {}
    if user_ids:
        names = {user.id: user.name for user in db.query(User).filter(User.id.in_(user_ids)).all()}

    presentation = analysis.presentation
    result = analysis.result

    return BusinessStatusStateResponse(
        id=analysis.id,
        business_status=analysis.business_status or BusinessStatus.EN_ANALISIS.value,
        presentation=(
            PresentationResponse(
                presented_at=presentation.presented_at,
                amount=_to_float(presentation.amount),
                currency=presentation.currency,
                channel=presentation.channel,
                offer_number=presentation.offer_number,
                notes=presentation.notes,
                receipt_filename=presentation.receipt_filename,
                updated_at=presentation.updated_at,
            )
            if presentation is not None
            else None
        ),
        result=(
            ResultResponse(
                outcome=result.outcome,
                resulted_at=result.resulted_at,
                awarded_amount=_to_float(result.awarded_amount),
                loss_reason=result.loss_reason,
                winner_name=result.winner_name,
                winner_amount=_to_float(result.winner_amount),
                notes=result.notes,
                updated_at=result.updated_at,
            )
            if result is not None
            else None
        ),
        history=[
            BusinessStatusHistoryItem(
                previous_status=row.previous_status,
                new_status=row.new_status,
                changed_by_name=names.get(row.changed_by) if row.changed_by else None,
                changed_at=row.changed_at,
                note=row.note,
            )
            for row in history_rows
        ],
    )


def _receipt_error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def _require_presentation(analysis: Analysis) -> AnalysisPresentation:
    presentation = analysis.presentation
    if presentation is None:
        raise _receipt_error(
            "PRESENTATION_NOT_FOUND",
            "Primero registrá la presentación para adjuntar la constancia",
            status.HTTP_400_BAD_REQUEST,
        )
    return presentation


def _safe_filename(filename: str | None) -> str:
    base = (filename or "constancia").replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "constancia"
    return cleaned[:150]


def _build_storage():
    from analysis.service.upload import _build_blob_storage

    return _build_blob_storage()


def save_presentation_receipt(
    db: Session,
    analysis: Analysis,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> None:
    presentation = _require_presentation(analysis)
    if content_type not in RECEIPT_CONTENT_TYPES:
        raise _receipt_error(
            "INVALID_RECEIPT_TYPE",
            "La constancia debe ser un PDF o una imagen (PNG, JPG o WEBP)",
            status.HTTP_400_BAD_REQUEST,
        )
    if not content:
        raise _receipt_error("EMPTY_RECEIPT", "El archivo está vacío", status.HTTP_400_BAD_REQUEST)
    if len(content) > RECEIPT_MAX_BYTES:
        raise _receipt_error(
            "RECEIPT_TOO_LARGE",
            "La constancia no puede superar los 10 MB",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    safe_name = _safe_filename(filename)
    blob_name = f"presentations/{analysis.id}/{uuid4().hex}_{safe_name}"
    storage = _build_storage()
    storage.upload(blob_name, content)

    previous_blob = presentation.receipt_blob_name
    presentation.receipt_blob_name = blob_name
    presentation.receipt_filename = safe_name
    presentation.receipt_content_type = content_type
    presentation.updated_at = datetime.now(UTC)
    db.commit()
    if previous_blob:
        storage.delete(previous_blob)
    db.refresh(analysis)


def remove_presentation_receipt(db: Session, analysis: Analysis) -> None:
    presentation = _require_presentation(analysis)
    blob_name = presentation.receipt_blob_name
    if blob_name is None:
        return
    presentation.receipt_blob_name = None
    presentation.receipt_filename = None
    presentation.receipt_content_type = None
    presentation.updated_at = datetime.now(UTC)
    db.commit()
    _build_storage().delete(blob_name)
    db.refresh(analysis)


def get_presentation_receipt_url(analysis: Analysis) -> ReceiptUrlResponse:
    presentation = analysis.presentation
    if presentation is None or presentation.receipt_blob_name is None:
        raise _receipt_error(
            "RECEIPT_NOT_FOUND",
            "La presentación no tiene constancia adjunta",
            status.HTTP_404_NOT_FOUND,
        )
    url = _build_storage().generate_download_url(presentation.receipt_blob_name)
    return ReceiptUrlResponse(url=url, filename=presentation.receipt_filename or "constancia")
