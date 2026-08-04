from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from analysis.metadata_persistence import persist_analysis_metadata
from analysis.models import CurrentStage
from analysis.schemas import (
    AnalysisCreateResponse,
    AnalysisStatusResponse,
    StartAnalysisRequest,
    StartAnalysisResponse,
)
from analysis.service import (
    IncomingUploadFile,
    create_analysis_with_documents,
    enqueue_analysis,
    find_duplicates_for_analysis,
    request_cancellation,
    to_document_response,
    validate_analysis_ownership,
)
from documents.models import Document
from extraction.ai_search import validate_index_contract
from shared.config import get_settings
from shared.database import get_db
from users.service import get_current_user, http_bearer

analysis_router = APIRouter(prefix="/analyses", tags=["analyses"])


@analysis_router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    files: Annotated[list[UploadFile], File(...)],
    primary_file_index: Annotated[int, Form()] = 0,
    credentials=Depends(http_bearer),
    db: Session = Depends(get_db),
) -> AnalysisCreateResponse:
    current_user = get_current_user(credentials, db)

    incoming_files: list[IncomingUploadFile] = []
    for file in files:
        incoming_files.append(
            IncomingUploadFile(
                filename=file.filename or "documento.pdf",
                content=await file.read(),
            )
        )

    analysis, documents, warnings = create_analysis_with_documents(
        db=db,
        user_id=current_user.id,
        files=incoming_files,
        primary_file_index=primary_file_index,
    )

    return AnalysisCreateResponse(
        id=analysis.id,
        status=analysis.status,
        documents=[to_document_response(document) for document in documents],
        warnings=warnings,
    )


@analysis_router.post("/{analysis_id}/start", response_model=StartAnalysisResponse)
async def start_analysis(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    payload: StartAnalysisRequest | None = None,
    credentials=Depends(http_bearer),
    db: Session = Depends(get_db),
) -> StartAnalysisResponse:
    settings = get_settings()
    if settings.is_production:
        settings.validate_cloud_configuration()
        validate_index_contract()

    current_user = get_current_user(credentials, db)
    analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

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
        cancelled_ids = [doc_id for doc_id, action in decision_map.items() if action == "cancel"]

        if cancelled_ids:
            docs_to_cancel = (
                db.query(Document)
                .filter(Document.id.in_(cancelled_ids), Document.analysis_id == analysis.id, Document.deleted_at.is_(None))
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

    db.refresh(analysis)
    docs = db.query(Document).filter(Document.analysis_id == analysis.id).all()
    persist_analysis_metadata(
        analysis=analysis,
        documents=docs,
        versions=[],
        event="analysis_queued",
    )

    enqueue_analysis(background_tasks, analysis_id)

    return StartAnalysisResponse(
        id=analysis.id,
        status=analysis.status,
        message="Análisis encolado exitosamente.",
    )


@analysis_router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    analysis_id: str,
    credentials=Depends(http_bearer),
    db: Session = Depends(get_db),
) -> AnalysisStatusResponse:
    current_user = get_current_user(credentials, db)
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


@analysis_router.post("/{analysis_id}/cancel", response_model=AnalysisStatusResponse)
async def cancel_analysis(
    analysis_id: str,
    credentials=Depends(http_bearer),
    db: Session = Depends(get_db),
) -> AnalysisStatusResponse:
    current_user = get_current_user(credentials, db)

    try:
        analysis = request_cancellation(db, analysis_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

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
        extracted_data=None,
        conflicts=None,
    )
