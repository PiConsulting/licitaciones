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

from analysis.cosmos_runtime import (
    cancel_analysis_cosmos,
    create_analysis_with_documents_cosmos,
    delete_analysis_cosmos,
    extract_and_index_cosmos,
    get_analysis_detail_cosmos,
    get_analysis_status_cosmos,
    list_analyses_cosmos,
    start_analysis_with_duplicates_cosmos,
)
from analysis.metadata_persistence import (
    persist_analysis_metadata,
    read_runtime_analysis_from_cosmos,
)
from analysis.models import CurrentStage
from analysis.schemas import (
    AnalysisCreateResponse,
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisStatusResponse,
    AnalysisVersionResponse,
    DocumentResponse,
    DuplicateWarning,
    StartAnalysisRequest,
    StartAnalysisResponse,
)
from analysis.service import (
    IncomingUploadFile,
    create_analysis_with_documents,
    delete_analysis,
    enqueue_analysis,
    find_duplicates_for_analysis,
    list_analyses,
    request_cancellation,
    to_document_response,
    validate_analysis_ownership,
)
from documents.models import Document
from extraction.ai_search import validate_index_contract
from shared.config import get_settings
from shared.database import SessionLocal
from users.service import get_current_user, http_bearer

analysis_router = APIRouter(prefix="/analyses", tags=["analyses"])


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
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    normalized_sort_order = "asc" if sort_order == "asc" else "desc"

    if settings.persistence_mode_normalized() == "cosmos_only":
        items, total = list_analyses_cosmos(
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
        total_pages = max(1, (total + per_page - 1) // per_page)
        return AnalysisListResponse(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        )

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
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    if settings.persistence_mode_normalized() == "cosmos_only":
        try:
            payload = get_analysis_detail_cosmos(analysis_id, current_user.id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}},
            ) from exc
        return AnalysisDetailResponse(**payload)

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
                detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
            )

        documents = [document for document in analysis.documents if document.deleted_at is None]

        return AnalysisDetailResponse(
            id=analysis.id,
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
        )
    finally:
        db.close()


@analysis_router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    files: Annotated[list[UploadFile], File(...)],
    primary_file_index: Annotated[int, Form()] = 0,
    credentials=Depends(http_bearer),
) -> AnalysisCreateResponse:
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    incoming_files: list[IncomingUploadFile] = []
    for file in files:
        incoming_files.append(
            IncomingUploadFile(
                filename=file.filename or "documento.pdf",
                content=await file.read(),
            )
        )

    if settings.persistence_mode_normalized() == "cosmos_only":
        try:
            result = create_analysis_with_documents_cosmos(
                user_id=current_user.id,
                user_name=current_user.name,
                files=incoming_files,
                primary_file_index=primary_file_index,
            )
        except ValueError as exc:
            error_code = str(exc)
            if error_code == "NO_FILES":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": {"code": "NO_FILES", "message": "Debés subir al menos un archivo"}},
                ) from exc
            if error_code == "TOO_MANY_FILES":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": {
                            "code": "TOO_MANY_FILES",
                            "message": f"Podés subir hasta 10 archivos por análisis y seleccionaste {len(incoming_files)}",
                        }
                    },
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "MISSING_PRIMARY", "message": "Seleccioná cuál es el pliego principal"}},
            ) from exc

        return AnalysisCreateResponse(
            id=result.analysis["analysis_id"],
            status=str(result.analysis["status"]),
            documents=[
                DocumentResponse(
                    id=str(document["document_id"]),
                    filename=str(document["filename"]),
                    page_count=int(document["page_count"]),
                    file_size_bytes=int(document["file_size_bytes"]),
                    is_primary=bool(document["is_primary"]),
                )
                for document in result.documents
            ],
            warnings=result.warnings,
            requires_resolution=bool(result.duplicates),
            duplicates=[DuplicateWarning(**item) for item in result.duplicates],
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
        validate_index_contract()

    current_user = get_current_user(credentials, None)

    if settings.persistence_mode_normalized() == "cosmos_only":
        decisions = [decision.model_dump() for decision in (payload.decisions if payload else [])]
        try:
            result = start_analysis_with_duplicates_cosmos(
                analysis_id,
                current_user.id,
                created_by_label=current_user.name or current_user.email,
                decisions=decisions,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}},
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ANALYSIS_ALREADY_STARTED",
                        "message": "El análisis ya fue iniciado",
                    }
                },
            ) from exc

        if result["status"] == "queued":
            background_tasks.add_task(extract_and_index_cosmos, analysis_id)

        return StartAnalysisResponse(
            id=str(result["id"]),
            status=str(result["status"]),
            message=str(result["message"]),
            requires_resolution=bool(result.get("requires_resolution", False)),
            duplicates=[DuplicateWarning(**item) for item in result.get("duplicates", [])],
            redirect_analysis_id=result.get("redirect_analysis_id"),
        )

    db = SessionLocal()
    try:
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
    finally:
        db.close()


@analysis_router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisStatusResponse:
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    if settings.persistence_mode_normalized() == "cosmos_only":
        try:
            payload = get_analysis_status_cosmos(analysis_id, current_user.id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}},
            ) from exc
        return AnalysisStatusResponse(**payload)

    db = SessionLocal()
    try:
        analysis = validate_analysis_ownership(db, analysis_id, current_user.id)

        if settings.is_production and settings.is_cosmos_temporal_mode():
            runtime_snapshot = read_runtime_analysis_from_cosmos(analysis_id)
            if runtime_snapshot is not None:
                return AnalysisStatusResponse(
                    id=runtime_snapshot["id"],
                    status=runtime_snapshot["status"],
                    current_stage=runtime_snapshot["current_stage"],
                    stage_progress=runtime_snapshot.get("stage_progress"),
                    progress_percentage=runtime_snapshot.get("progress_percentage", 0),
                    started_at=runtime_snapshot.get("started_at"),
                    timeout_at=runtime_snapshot.get("timeout_at"),
                    timeout_warning_at=runtime_snapshot.get("timeout_warning_at"),
                    error_message=runtime_snapshot.get("error_message"),
                    extracted_data=runtime_snapshot.get("extracted_data"),
                    conflicts=runtime_snapshot.get("conflicts"),
                )

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


@analysis_router.post("/{analysis_id}/cancel", response_model=AnalysisStatusResponse)
async def cancel_analysis(
    analysis_id: str,
    credentials=Depends(http_bearer),
) -> AnalysisStatusResponse:
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    if settings.persistence_mode_normalized() == "cosmos_only":
        try:
            payload = cancel_analysis_cosmos(analysis_id, current_user.id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return AnalysisStatusResponse(**payload)

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
    settings = get_settings()
    current_user = get_current_user(credentials, None)

    if settings.persistence_mode_normalized() == "cosmos_only":
        try:
            delete_analysis_cosmos(analysis_id, current_user.id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}},
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ANALYSIS_DELETE_NOT_ALLOWED",
                        "message": "No podés eliminar un análisis en curso",
                    }
                },
            ) from exc
        return None

    db = SessionLocal()
    try:
        delete_analysis(db, analysis_id, current_user.id)
    finally:
        db.close()
    return None
