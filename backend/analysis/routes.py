from datetime import UTC, date, datetime
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
    AnalysisCreateResponse,
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisStatusResponse,
    AnalysisVersionResponse,
    DuplicateWarning,
    StartAnalysisRequest,
    StartAnalysisResponse,
)
from analysis.service import (
    IncomingUploadFile,
    create_analysis_with_documents,
    delete_analysis,
    enqueue_analysis,
    enqueue_analysis_categories,
    find_duplicates_for_analysis,
    list_analyses,
    request_cancellation,
    to_document_response,
    validate_analysis_ownership,
)
from documents.models import Document
from infra.config import get_settings
from infra.database import SessionLocal
from tracking.service import get_tracking
from users.service import get_current_user, http_bearer

analysis_router = APIRouter(prefix="/analyses", tags=["analyses"])


def _normalize_analysis_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:160] if cleaned else None


@analysis_router.get("", response_model=AnalysisListResponse)
async def get_analyses(
    search: str | None = None,
    analysis_status: str | None = Query(default=None, alias="status"),
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


@analysis_router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis_detail(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisDetailResponse:
    current_user = get_current_user(credentials, None)

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
                    "error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}
                },
            )

        documents = [document for document in analysis.documents if document.deleted_at is None]

        return AnalysisDetailResponse(
            id=analysis.id,
            analysis_name=analysis.analysis_name,
            created_at=analysis.created_at,
            status=analysis.status,
            current_stage=analysis.current_stage,
            created_by=analysis.created_by,
            current_version=AnalysisVersionResponse(
                id=current_version.id,
                version_number=current_version.version_number,
                extracted_data=current_version.extracted_data,
                conflicts=current_version.conflicts,
                created_at=current_version.created_at,
                created_by=current_version.created_by,
            ),
            documents=[to_document_response(document) for document in documents],
            tracking=get_tracking(analysis_id, current_user.id),
        )
    finally:
        db.close()


@analysis_router.post(
    "", response_model=AnalysisCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_analysis(
    files: Annotated[list[UploadFile], File(...)],
    primary_file_index: Annotated[int, Form()] = 0,
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
        )
    finally:
        db.close()


@analysis_router.post("/{analysis_id}/start-categories", response_model=StartAnalysisResponse)
async def start_analysis_categories(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    credentials=Depends(http_bearer),
) -> StartAnalysisResponse:
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
                        "message": "El análisis debe estar en estado en_revision para iniciar categorías",
                    }
                },
            )

        next_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": build_stage_progress(CurrentStage.QUEUED),
        }

        updated_rows = (
            db.query(Analysis)
            .filter(
                Analysis.id == analysis.id,
                Analysis.created_by == current_user.id,
                Analysis.deleted_at.is_(None),
                Analysis.status == "en_revision",
            )
            .update(
                {
                    Analysis.status: "queued",
                    Analysis.current_stage: CurrentStage.QUEUED.value,
                    Analysis.progress_percentage: 0,
                    Analysis.cancellation_requested: False,
                    Analysis.error_message: None,
                    Analysis.updated_at: datetime.now(UTC),
                    Analysis.extraction_metadata: next_metadata,
                },
                synchronize_session=False,
            )
        )

        if updated_rows == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "ANALYSIS_CATEGORIES_ALREADY_STARTED",
                        "message": "El análisis ya no está en revisión para iniciar categorías",
                    }
                },
            )

        db.commit()
        db.refresh(analysis)

        enqueue_analysis_categories(background_tasks, analysis_id)

        return StartAnalysisResponse(
            id=analysis.id,
            status=analysis.status,
            message="Análisis de categorías encolado exitosamente.",
        )
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
