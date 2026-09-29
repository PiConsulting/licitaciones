from datetime import UTC, date, datetime
import json
import logging
from pathlib import Path
import re
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from analysis.models import Analysis, CurrentStage
from analysis.progress import build_stage_progress
from analysis.schemas import (
    AnalysisBusinessUnitItem,
    AnalysisCreateResponse,
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisPatchRequest,
    AnalysisPatchResponse,
    AnalysisStatusResponse,
    AnalysisVersionResponse,
    BusinessStatusStateResponse,
    BusinessStatusSummaryResponse,
    BusinessStatusUpdateRequest,
    BusinessStatusUpdateResponse,
    CategoriesDecisionRequest,
    CategoriesDecisionResponse,
    DuplicateWarning,
    PresentationRequest,
    ReanalyzeRequest,
    ReanalyzeResponse,
    ReceiptUrlResponse,
    ResultRequest,
    StartAnalysisRequest,
    StartAnalysisResponse,
    UpcomingEventItem,
)
from analysis.service import (
    UPCOMING_EVENTS_WINDOW_DAYS,
    IncomingUploadFile,
    apply_categories_decision,
    build_business_state,
    create_analysis_with_documents,
    delete_analysis,
    enqueue_analysis,
    enqueue_analysis_categories,
    enqueue_reanalyze,
    find_duplicates_for_analysis,
    get_business_status_summary,
    get_presentation_receipt_url,
    is_valid_business_status_transition,
    list_analyses,
    list_business_units,
    list_upcoming_events,
    remove_presentation_receipt,
    request_cancellation,
    save_presentation,
    save_presentation_receipt,
    save_result,
    sync_business_status,
    to_document_response,
    update_business_status,
    validate_analysis_ownership,
)
from documents.models import Document
from infra.config import get_settings
from infra.database import SessionLocal
from tracking.service import get_tracking
from users.models import User
from users.service import get_current_user, http_bearer

analysis_router = APIRouter(prefix="/analyses", tags=["analyses"])
logger = logging.getLogger(__name__)

_CATEGORY_DEFINITIONS_PATH = (
    Path(__file__).resolve().parent / "extraction" / "category_definitions.json"
)
_PHASE1_CATEGORIES = [
    "preview_criterios",
    "objeto_alcance",
    "identificacion_procedimiento",
    "requisitos_admisibilidad",
    "plazos_clave",
    "garantias",
    "riesgos",
]
_PHASE2_CATEGORIES = [
    "causales_rechazo",
    "anexos_obligatorios",
    "criterios_evaluacion",
    "eventos_temporales",
    "plazos_relativos",
]

_PRESUPUESTO_RE = re.compile(r"presupuesto", re.IGNORECASE)


def _allowed_reanalysis_categories() -> set[str]:
    try:
        data = json.loads(_CATEGORY_DEFINITIONS_PATH.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("reanalysis_categories_catalog_missing", extra={"path": str(_CATEGORY_DEFINITIONS_PATH)})
        return set(_PHASE1_CATEGORIES + _PHASE2_CATEGORIES)
    except json.JSONDecodeError:
        logger.warning("reanalysis_categories_catalog_invalid_json", extra={"path": str(_CATEGORY_DEFINITIONS_PATH)})
        return set(_PHASE1_CATEGORIES + _PHASE2_CATEGORIES)
    return {str(key) for key in data.keys() if key != "_comment"}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _resolve_reanalysis_categories(reanalysis_type: str, requested: list[str]) -> list[str]:
    if reanalysis_type == "phase1":
        return list(_PHASE1_CATEGORIES)
    if reanalysis_type == "phase2":
        return list(_PHASE2_CATEGORIES)
    if reanalysis_type == "all":
        return list(_PHASE1_CATEGORIES + _PHASE2_CATEGORIES)
    return list(requested)


def _normalize_analysis_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:160] if cleaned else None


def _normalize_currency(value: str) -> str:
    return value.strip().upper()


def _format_manual_budget_value(amount: float, currency: str) -> str:
    # Notación argentina (miles con punto, decimales con coma), manteniendo la moneda explícita.
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{currency} {formatted}"


def _upsert_presupuesto_item(
    extracted_data: dict,
    *,
    amount: float,
    currency: str,
    user_id: str,
    edited_at_iso: str,
) -> None:
    budget_value = _format_manual_budget_value(amount, currency)

    budget_item = {
        "tipo": "presupuesto_oficial",
        "valor": budget_value,
        "confidence": 1.0,
        "extraction_status": "success",
        "source_references": [],
        "modified_by": user_id,
        "modified_at": edited_at_iso,
        "monto_estimado": amount,
        "moneda": currency,
        "monto_estimado_source": "manual",
    }

    datos_procedimiento = extracted_data.get("datos_procedimiento")
    items = list(datos_procedimiento) if isinstance(datos_procedimiento, list) else []
    target = next(
        (
            index
            for index, item in enumerate(items)
            if isinstance(item, dict) and _PRESUPUESTO_RE.search(str(item.get("tipo") or ""))
        ),
        None,
    )
    if target is None:
        items.append(budget_item)
    else:
        items[target] = budget_item
    extracted_data["datos_procedimiento"] = items

    extracted_data["monto_estimado"] = amount
    extracted_data["moneda"] = currency
    extracted_data["monto_estimado_source"] = "manual"


@analysis_router.get("", response_model=AnalysisListResponse)
async def get_analyses(
    search: str | None = None,
    analysis_status: str | None = Query(default=None, alias="status"),
    business_unit: str | None = Query(default=None, alias="business_unit"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    credentials=Depends(http_bearer),
) -> AnalysisListResponse:
    current_user = get_current_user(credentials, None)

    normalized_sort_order = "asc" if sort_order == "asc" else "desc"

    db = SessionLocal()
    try:
        items, total = list_analyses(
            db,
            user_id=current_user.id,
            search=search,
            status_filter=analysis_status,
            business_unit_filter=business_unit,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            sort_order=normalized_sort_order,
        )
    finally:
        db.close()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return AnalysisListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@analysis_router.get("/units", response_model=list[AnalysisBusinessUnitItem])
async def get_analysis_business_units(
    search: str | None = None,
    analysis_status: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    credentials=Depends(http_bearer),
) -> list[AnalysisBusinessUnitItem]:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        units = list_business_units(
            db,
            user_id=current_user.id,
            search=search,
            status_filter=analysis_status,
            date_from=date_from,
            date_to=date_to,
        )
    finally:
        db.close()

    return [AnalysisBusinessUnitItem(**item) for item in units]


@analysis_router.get("/business-status-summary", response_model=BusinessStatusSummaryResponse)
async def get_business_status_summary_route(
    business_unit: str | None = Query(default=None, alias="business_unit"),
    date_from: date | None = None,
    date_to: date | None = None,
    credentials=Depends(http_bearer),
) -> BusinessStatusSummaryResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        summary = get_business_status_summary(
            db,
            user_id=current_user.id,
            business_unit=business_unit,
            date_from=date_from,
            date_to=date_to,
        )
    finally:
        db.close()

    return BusinessStatusSummaryResponse(**summary)


@analysis_router.get("/upcoming-events", response_model=list[UpcomingEventItem])
async def get_upcoming_events_route(
    days: int = Query(default=UPCOMING_EVENTS_WINDOW_DAYS, ge=1, le=60),
    credentials=Depends(http_bearer),
) -> list[UpcomingEventItem]:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        items = list_upcoming_events(db, user_id=current_user.id, days=days)
    finally:
        db.close()

    return [UpcomingEventItem(**item) for item in items]


@analysis_router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis_detail(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisDetailResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        sync_business_status(db, analysis, current_user.id)

        current_version = None
        if analysis.current_version_id:
            for version in analysis.versions:
                if version.id == analysis.current_version_id:
                    current_version = version
                    break

        if current_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}
                },
            )

        documents = [document for document in analysis.documents if document.deleted_at is None]
        versions = sorted(
            analysis.versions,
            key=lambda version: int(version.version_number or 0),
            reverse=True,
        )

        creator = db.query(User).filter(User.id == analysis.created_by).first()

        return AnalysisDetailResponse(
            id=analysis.id,
            analysis_name=analysis.analysis_name,
            business_unit=analysis.business_unit,
            created_at=analysis.created_at,
            status=analysis.status,
            current_stage=analysis.current_stage,
            created_by=analysis.created_by,
            created_by_name=creator.name if creator else None,
            categories_decision=analysis.categories_decision,
            categories_decision_by_name=analysis.categories_decision_by_name,
            categories_decision_at=analysis.categories_decision_at,
            business_status=analysis.business_status,
            current_version=AnalysisVersionResponse(
                id=current_version.id,
                version_number=current_version.version_number,
                extracted_data=current_version.extracted_data,
                conflicts=current_version.conflicts,
                created_at=current_version.created_at,
                created_by=current_version.created_by,
            ),
            versions=[
                AnalysisVersionResponse(
                    id=version.id,
                    version_number=version.version_number,
                    extracted_data=version.extracted_data,
                    conflicts=version.conflicts,
                    created_at=version.created_at,
                    created_by=version.created_by,
                )
                for version in versions
            ],
            documents=[to_document_response(document) for document in documents],
            tracking=get_tracking(analysis_id, current_user.id),
        )
    finally:
        db.close()


@analysis_router.patch("/{analysis_id}", response_model=AnalysisPatchResponse)
async def patch_analysis(
    analysis_id: str,
    payload: AnalysisPatchRequest,
    credentials=Depends(http_bearer),
) -> AnalysisPatchResponse:
    current_user = get_current_user(credentials, None)
    normalized_currency = _normalize_currency(payload.moneda)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

        current_version = None
        if analysis.current_version_id:
            for version in analysis.versions:
                if version.id == analysis.current_version_id:
                    current_version = version
                    break

        if current_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "ANALYSIS_NOT_FOUND",
                        "message": "Análisis no encontrado",
                    }
                },
            )

        extracted_data = dict(current_version.extracted_data or {})
        now = datetime.now(UTC)
        _upsert_presupuesto_item(
            extracted_data,
            amount=payload.monto_estimado,
            currency=normalized_currency,
            user_id=current_user.id,
            edited_at_iso=now.isoformat(),
        )
        current_version.extracted_data = extracted_data
        analysis.updated_at = now

        db.commit()

        return AnalysisPatchResponse(
            id=analysis.id,
            monto_estimado=payload.monto_estimado,
            moneda=normalized_currency,
            monto_estimado_source="manual",
            message="Monto estimado actualizado manualmente.",
        )
    finally:
        db.close()


@analysis_router.post(
    "", response_model=AnalysisCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_analysis(
    files: Annotated[list[UploadFile], File(...)],
    primary_file_index: Annotated[int, Form()] = 0,
    analysis_name: Annotated[str | None, Form()] = None,
    business_unit: Annotated[str | None, Form()] = None,
    credentials=Depends(http_bearer),
) -> AnalysisCreateResponse:
    current_user = get_current_user(credentials, None)

    incoming_files: list[IncomingUploadFile] = []
    for file in files:
        incoming_files.append(
            IncomingUploadFile(
                filename=file.filename or "documento.pdf",
                content=await file.read(),
            )
        )

    db = SessionLocal()
    try:
        analysis, documents, warnings, duplicates = create_analysis_with_documents(
            db=db,
            user_id=current_user.id,
            files=incoming_files,
            primary_file_index=primary_file_index,
            analysis_name=_normalize_analysis_name(analysis_name),
            business_unit=business_unit.strip()[:80] if business_unit and business_unit.strip() else None,
        )
    finally:
        db.close()

    return AnalysisCreateResponse(
        id=analysis.id,
        status=analysis.status,
        documents=[to_document_response(document) for document in documents],
        warnings=warnings,
        requires_resolution=bool(duplicates),
        duplicates=[DuplicateWarning(**item) for item in duplicates],
    )


@analysis_router.post("/{analysis_id}/start", response_model=StartAnalysisResponse)
async def start_analysis(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    payload: StartAnalysisRequest | None = None,
    credentials=Depends(http_bearer),
) -> StartAnalysisResponse:
    settings = get_settings()
    if settings.is_production:
        settings.validate_cloud_configuration()

    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        analysis_name = _normalize_analysis_name(payload.analysis_name if payload else None)
        if analysis.status not in {"draft", "error"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ANALYSIS_ALREADY_STARTED",
                        "message": f"El análisis ya está {analysis.status}",
                    }
                },
            )

        if analysis_name is not None:
            analysis.analysis_name = analysis_name

        duplicates = find_duplicates_for_analysis(db, analysis.id, current_user.id)

        if duplicates:
            decisions = payload.decisions if payload else []
            decision_map = {decision.document_id: decision.action for decision in decisions}
            unresolved = [item for item in duplicates if item["document_id"] not in decision_map]

            if unresolved:
                return StartAnalysisResponse(
                    id=analysis.id,
                    status=analysis.status,
                    message="Se detectaron documentos duplicados. Elegí qué hacer con cada uno.",
                    requires_resolution=True,
                    duplicates=duplicates,
                )

            redirect_target: str | None = None
            cancelled_ids = [
                doc_id for doc_id, action in decision_map.items() if action == "cancel"
            ]

            if cancelled_ids:
                docs_to_cancel = (
                    db.query(Document)
                    .filter(
                        Document.id.in_(cancelled_ids),
                        Document.analysis_id == analysis.id,
                        Document.deleted_at.is_(None),
                    )
                    .all()
                )
                for document in docs_to_cancel:
                    document.deleted_at = datetime.now(UTC)

            for duplicate in duplicates:
                if decision_map[duplicate["document_id"]] == "view_existing":
                    redirect_target = duplicate["existing_analysis_id"]
                    break

            remaining_docs = (
                db.query(Document)
                .filter(Document.analysis_id == analysis.id, Document.deleted_at.is_(None))
                .count()
            )
            if remaining_docs == 0:
                db.commit()
                return StartAnalysisResponse(
                    id=analysis.id,
                    status=analysis.status,
                    message="No quedan documentos para analizar. Podés volver al wizard y subir otros archivos.",
                    redirect_analysis_id=redirect_target,
                )

            if redirect_target:
                db.commit()
                return StartAnalysisResponse(
                    id=analysis.id,
                    status=analysis.status,
                    message="Redirigiendo al análisis existente.",
                    redirect_analysis_id=redirect_target,
                )

        analysis.status = "queued"
        analysis.current_stage = CurrentStage.QUEUED.value
        analysis.progress_percentage = 0
        analysis.cancellation_requested = False
        analysis.error_message = None
        analysis.extraction_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": "En cola",
        }
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        enqueue_analysis(background_tasks, analysis_id)

        return StartAnalysisResponse(
            id=analysis.id,
            status=analysis.status,
            message="Análisis encolado exitosamente.",
        )
    finally:
        db.close()


@analysis_router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisStatusResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

        extracted_data = None
        conflicts = None
        if analysis.current_version_id:
            for version in analysis.versions:
                if version.id == analysis.current_version_id:
                    extracted_data = version.extracted_data
                    conflicts = version.conflicts
                    break

        return AnalysisStatusResponse(
            id=analysis.id,
            status=analysis.status,
            current_stage=analysis.current_stage,
            stage_progress=(analysis.extraction_metadata or {}).get("stage_progress"),
            progress_percentage=analysis.progress_percentage or 0,
            started_at=analysis.started_at,
            timeout_at=analysis.timeout_at,
            timeout_warning_at=analysis.timeout_warning_at,
            error_message=analysis.error_message,
            extracted_data=extracted_data,
            conflicts=conflicts,
            reanalysis_type=(analysis.extraction_metadata or {}).get("reanalysis_type"),
            reanalysis_categories=list((analysis.extraction_metadata or {}).get("reanalysis_categories") or []),
            reanalysis_started_at=_parse_iso_datetime((analysis.extraction_metadata or {}).get("reanalysis_started_at")),
        )
    finally:
        db.close()


@analysis_router.post("/{analysis_id}/reanalyze", response_model=ReanalyzeResponse)
async def reanalyze_analysis(
    analysis_id: str,
    payload: ReanalyzeRequest,
    background_tasks: BackgroundTasks,
    credentials=Depends(http_bearer),
) -> ReanalyzeResponse:
    current_user = get_current_user(credentials, None)
    allowed_statuses = {"analyzed", "validated", "en_revision", "error"}

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

        if analysis.status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ANALYSIS_REANALYZE_NOT_ALLOWED",
                        "message": (
                            "El análisis debe estar en estado analyzed, validated, en_revision o error "
                            "para reanalizar"
                        ),
                    }
                },
            )

        categories = payload.categories or []
        if payload.reanalysis_type == "categories":
            if not categories:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": {
                            "code": "REANALYZE_CATEGORIES_REQUIRED",
                            "message": "Debés seleccionar al menos una categoría para reanalizar",
                        }
                    },
                )

            allowed_categories = _allowed_reanalysis_categories()
            invalid = [category for category in categories if category not in allowed_categories]
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": {
                            "code": "REANALYZE_CATEGORIES_INVALID",
                            "message": (
                                "Hay categorías inválidas en la solicitud: "
                                + ", ".join(sorted(set(invalid)))
                            ),
                        }
                    },
                )

        effective_categories = _resolve_reanalysis_categories(payload.reanalysis_type, categories)
        source_version_id = analysis.current_version_id
        source_status = analysis.status

        analysis.status = "queued"
        analysis.current_stage = CurrentStage.QUEUED.value
        analysis.progress_percentage = 0
        analysis.cancellation_requested = False
        analysis.error_message = None
        analysis.extraction_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": "En cola",
            "reanalysis_type": payload.reanalysis_type,
            "reanalysis_categories": effective_categories,
            "reanalysis_started_at": datetime.now(UTC).isoformat(),
            # Permite que cancelar este reanálisis revierta al status/versión previos en vez de marcar todo el análisis "cancelled".
            "reanalysis_source_status": source_status,
            "reanalysis_source_version_id": source_version_id,
        }
        analysis.updated_at = datetime.now(UTC)
        db.commit()

        enqueue_reanalyze(background_tasks, analysis.id, payload.reanalysis_type, effective_categories)

        return ReanalyzeResponse(
            id=analysis.id,
            status=analysis.status,
            message="Reanálisis encolado exitosamente.",
            reanalysis_type=payload.reanalysis_type,
            categories=effective_categories,
            source_version_id=source_version_id,
            target_version_id=None,
            target_version_number=None,
        )
    finally:
        db.close()


@analysis_router.post(
    "/{analysis_id}/categories-decision", response_model=CategoriesDecisionResponse
)
async def decide_analysis_categories(
    analysis_id: str,
    payload: CategoriesDecisionRequest,
    background_tasks: BackgroundTasks,
    credentials=Depends(http_bearer),
) -> CategoriesDecisionResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        if analysis.status != "en_revision":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ANALYSIS_NOT_IN_REVIEW",
                        "message": "El análisis debe estar en estado en_revision para decidir sobre las categorías",
                    }
                },
            )

        decision_at = datetime.now(UTC)
        decision_values = {
            Analysis.categories_decision: payload.decision,
            Analysis.categories_decision_by: current_user.id,
            Analysis.categories_decision_by_name: current_user.name,
            Analysis.categories_decision_at: decision_at,
            Analysis.updated_at: decision_at,
        }

        if payload.decision == "approved":
            next_metadata = {
                **(analysis.extraction_metadata or {}),
                "stage_progress": build_stage_progress(CurrentStage.QUEUED),
            }
            decision_values.update(
                {
                    Analysis.status: "queued",
                    Analysis.current_stage: CurrentStage.QUEUED.value,
                    Analysis.progress_percentage: 0,
                    Analysis.cancellation_requested: False,
                    Analysis.error_message: None,
                    Analysis.extraction_metadata: next_metadata,
                }
            )

        updated_rows = (
            db.query(Analysis)
            .filter(
                Analysis.id == analysis.id,
                Analysis.created_by == current_user.id,
                Analysis.deleted_at.is_(None),
                Analysis.status == "en_revision",
            )
            .update(decision_values, synchronize_session=False)
        )

        if updated_rows == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "ANALYSIS_CATEGORIES_ALREADY_STARTED",
                        "message": "El análisis ya no está en revisión para decidir sobre las categorías",
                    }
                },
            )

        db.commit()
        db.refresh(analysis)
        apply_categories_decision(db, analysis, payload.decision, current_user.id)

        if payload.decision == "approved":
            enqueue_analysis_categories(background_tasks, analysis_id)
            message = "Análisis de categorías encolado exitosamente."
        else:
            message = "Decisión registrada: no se van a analizar las categorías restantes."

        return CategoriesDecisionResponse(
            id=analysis.id,
            status=analysis.status,
            message=message,
            decision=payload.decision,
            decision_by_name=analysis.categories_decision_by_name,
            decision_at=analysis.categories_decision_at,
        )
    finally:
        db.close()


@analysis_router.patch(
    "/{analysis_id}/business-status", response_model=BusinessStatusUpdateResponse
)
async def update_analysis_business_status(
    analysis_id: str,
    payload: BusinessStatusUpdateRequest,
    credentials=Depends(http_bearer),
) -> BusinessStatusUpdateResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

        if not is_valid_business_status_transition(
            analysis.business_status, payload.business_status
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "INVALID_BUSINESS_STATUS_TRANSITION",
                        "message": (
                            f"No se puede pasar de '{analysis.business_status or 'sin estado'}' "
                            f"a '{payload.business_status}'"
                        ),
                    }
                },
            )

        history_entry = update_business_status(
            db,
            analysis=analysis,
            target_status=payload.business_status,
            user_id=current_user.id,
            note=payload.note,
        )

        return BusinessStatusUpdateResponse(
            id=analysis.id,
            business_status=analysis.business_status,
            previous_status=history_entry.previous_status,
            changed_by_name=current_user.name,
            changed_at=history_entry.changed_at,
            message="Estado de negocio actualizado.",
        )
    finally:
        db.close()


@analysis_router.get(
    "/{analysis_id}/business-status", response_model=BusinessStatusStateResponse
)
async def get_analysis_business_state(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> BusinessStatusStateResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        sync_business_status(db, analysis, current_user.id)
        return build_business_state(db, analysis)
    finally:
        db.close()


@analysis_router.put(
    "/{analysis_id}/presentation", response_model=BusinessStatusStateResponse
)
async def put_analysis_presentation(
    analysis_id: str,
    payload: PresentationRequest,
    credentials=Depends(http_bearer),
) -> BusinessStatusStateResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        save_presentation(db, analysis, current_user, payload)
        return build_business_state(db, analysis)
    finally:
        db.close()


@analysis_router.post(
    "/{analysis_id}/presentation/receipt", response_model=BusinessStatusStateResponse
)
async def post_presentation_receipt(
    analysis_id: str,
    file: Annotated[UploadFile, File(...)],
    credentials=Depends(http_bearer),
) -> BusinessStatusStateResponse:
    current_user = get_current_user(credentials, None)
    content = await file.read()

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        save_presentation_receipt(db, analysis, file.filename, file.content_type, content)
        return build_business_state(db, analysis)
    finally:
        db.close()


@analysis_router.delete(
    "/{analysis_id}/presentation/receipt", response_model=BusinessStatusStateResponse
)
async def delete_presentation_receipt(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> BusinessStatusStateResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        remove_presentation_receipt(db, analysis)
        return build_business_state(db, analysis)
    finally:
        db.close()


@analysis_router.get(
    "/{analysis_id}/presentation/receipt", response_model=ReceiptUrlResponse
)
async def get_presentation_receipt(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> ReceiptUrlResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        return get_presentation_receipt_url(analysis)
    finally:
        db.close()


@analysis_router.put("/{analysis_id}/result", response_model=BusinessStatusStateResponse)
async def put_analysis_result(
    analysis_id: str,
    payload: ResultRequest,
    credentials=Depends(http_bearer),
) -> BusinessStatusStateResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)
        save_result(db, analysis, current_user, payload)
        return build_business_state(db, analysis)
    finally:
        db.close()


@analysis_router.post("/{analysis_id}/cancel", response_model=AnalysisStatusResponse)
async def cancel_analysis(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisStatusResponse:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        analysis = request_cancellation(db, analysis_id, current_user.id)
        response = AnalysisStatusResponse(
            id=analysis.id,
            status=analysis.status,
            current_stage=analysis.current_stage,
            stage_progress=(analysis.extraction_metadata or {}).get("stage_progress"),
            progress_percentage=analysis.progress_percentage or 0,
            started_at=analysis.started_at,
            timeout_at=analysis.timeout_at,
            timeout_warning_at=analysis.timeout_warning_at,
            error_message=analysis.error_message,
            extracted_data=None,
            conflicts=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    finally:
        db.close()
    return response


@analysis_router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_analysis(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> None:
    current_user = get_current_user(credentials, None)

    db = SessionLocal()
    try:
        delete_analysis(db, analysis_id, current_user.id)
    finally:
        db.close()
    return None
