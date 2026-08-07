from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import datetime as dt_parse
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import structlog

from analysis.extraction.graph import graph
from analysis.models import CurrentStage
from analysis.progress import build_stage_progress, calculate_timeout_minutes
from analysis.service import (
    MAX_FILES,
    IncomingUploadFile,
    _build_blob_storage,
    _extract_organism,
    _validate_pdf_or_raise,
)
from analysis.utils import calculate_confidence_avg
from documents.schemas import DocumentWarning
from documents.service import calculate_content_hash
from extraction.ai_search import upload_chunks
from extraction.chunking import create_chunks
from extraction.document_intelligence import extract_text
from extraction.embeddings import generate_embeddings
from shared.cosmos_container import get_cosmos_container

logger = structlog.get_logger(__name__)

_PROMPT_COST_PER_1K = 0.00015
_COMPLETION_COST_PER_1K = 0.0006
_TOTAL_CATEGORIES = 8


@dataclass
class CosmosAnalysisResult:
    analysis: dict
    documents: list[dict]
    warnings: list[DocumentWarning]


def _sanitize_filename(filename: str) -> str:
    sanitized = Path(filename).name
    return sanitized[:255]


def _compute_cost(metadata: dict) -> dict:
    usage_by_category = metadata.get("token_usage", {}) if metadata else {}
    prompt_tokens = sum(int(item.get("prompt_tokens", 0)) for item in usage_by_category.values())
    completion_tokens = sum(int(item.get("completion_tokens", 0)) for item in usage_by_category.values())
    total_tokens = sum(int(item.get("total_tokens", 0)) for item in usage_by_category.values())
    total_cost = ((prompt_tokens / 1000) * _PROMPT_COST_PER_1K) + ((completion_tokens / 1000) * _COMPLETION_COST_PER_1K)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 8),
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return dt_parse.fromisoformat(value)
    except ValueError:
        return None


def _analysis_item_id(analysis_id: str) -> str:
    return f"analysis::{analysis_id}"


def _analysis_partition_key_candidates(analysis_id: str) -> list[str]:
    return [analysis_id, _analysis_item_id(analysis_id)]


def _load_analysis_or_none(analysis_id: str) -> dict | None:
    container = get_cosmos_container()
    item_id = _analysis_item_id(analysis_id)
    for partition_key in _analysis_partition_key_candidates(analysis_id):
        try:
            return container.read_item(item=item_id, partition_key=partition_key)
        except Exception:  # noqa: BLE001
            logger.debug(
                "cosmos_analysis_read_fallback_failed",
                analysis_id=analysis_id,
                attempted_partition_key=partition_key,
            )
            continue

    rows = list(
        container.query_items(
            query="SELECT TOP 1 * FROM c WHERE c.type = 'analysis' AND c.analysis_id = @analysis_id",
            parameters=[{"name": "@analysis_id", "value": analysis_id}],
            enable_cross_partition_query=True,
        )
    )
    if rows:
        return rows[0]
    return None


def _upsert_analysis(analysis: dict, event: str) -> None:
    analysis["event"] = event
    analysis["updated_at"] = datetime.now(UTC).isoformat()
    get_cosmos_container().upsert_item(analysis)


def _query_documents(analysis_id: str, *, include_deleted: bool = False) -> list[dict]:
    container = get_cosmos_container()
    query = "SELECT * FROM c WHERE c.type = 'document' AND c.analysis_id = @analysis_id"
    if not include_deleted:
        query += " AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
    query += " ORDER BY c.uploaded_at ASC"
    return list(
        container.query_items(
            query=query,
            parameters=[{"name": "@analysis_id", "value": analysis_id}],
            partition_key=analysis_id,
        )
    )


def _get_latest_version(analysis_id: str) -> dict | None:
    container = get_cosmos_container()
    versions = list(
        container.query_items(
            query=(
                "SELECT TOP 1 * FROM c WHERE c.type = 'analysis_version' AND c.analysis_id = @analysis_id "
                "ORDER BY c.version_number DESC"
            ),
            parameters=[{"name": "@analysis_id", "value": analysis_id}],
            partition_key=analysis_id,
        )
    )
    return versions[0] if versions else None


def _fetch_analysis_enrichment(analysis: dict) -> tuple[list[dict], object]:
    analysis_id = str(analysis.get("analysis_id"))
    documents = _query_documents(analysis_id)
    extracted_data = None
    if analysis.get("current_version_id"):
        latest_version = _get_latest_version(analysis_id)
        extracted_data = (latest_version or {}).get("extracted_data")
    return documents, extracted_data


def _build_analysis_list_item(analysis: dict, documents: list[dict], extracted_data: object) -> dict:
    analysis_id = str(analysis.get("analysis_id"))
    primary_document_name = next(
        (document.get("filename") for document in documents if document.get("is_primary")),
        None,
    )

    metadata = analysis.get("extraction_metadata") or {}
    raw_stage_progress = metadata.get("stage_progress")
    stage_progress = raw_stage_progress if isinstance(raw_stage_progress, str) else None

    # Obtener el nombre del usuario desde Cosmos
    created_by_name = analysis.get("created_by_name")

    return {
        "id": analysis_id,
        "status": analysis.get("status", "draft"),
        "current_stage": analysis.get("current_stage", CurrentStage.QUEUED.value),
        "stage_progress": stage_progress,
        "progress_percentage": int(analysis.get("progress_percentage", 0) or 0),
        "created_at": _parse_dt(analysis.get("created_at")),
        "primary_document_name": primary_document_name,
        "organismo": _extract_organism(extracted_data),
        "created_by_name": created_by_name,
    }


def list_analyses_cosmos(
    *,
    user_id: str,
    search: str | None = None,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    container = get_cosmos_container()

    query = "SELECT * FROM c WHERE c.type = 'analysis' AND c.created_by = @user_id"
    parameters: list[dict] = [{"name": "@user_id", "value": user_id}]

    if status_filter:
        query += " AND c.status = @status"
        parameters.append({"name": "@status", "value": status_filter})

    if date_from:
        date_from_iso = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC).isoformat()
        query += " AND c.created_at >= @date_from"
        parameters.append({"name": "@date_from", "value": date_from_iso})

    if date_to:
        date_to_iso = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC).isoformat()
        query += " AND c.created_at <= @date_to"
        parameters.append({"name": "@date_to", "value": date_to_iso})

    analyses = list(
        container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)
    )

    sort_key_fns = {
        "created_at": lambda item: item.get("created_at") or "",
        "status": lambda item: item.get("status", "draft") or "",
        "current_stage": lambda item: item.get("current_stage", CurrentStage.QUEUED.value) or "",
    }
    key_fn = sort_key_fns.get(sort_by, sort_key_fns["created_at"])
    analyses.sort(key=key_fn, reverse=(sort_order != "asc"))

    normalized_search = search.strip().lower() if search and search.strip() else None

    # Sorting only needs fields already present on the analysis item, so when there's
    # no search term we can page first and only fetch documents/versions (the
    # expensive per-item lookups) for the page actually being returned.
    if normalized_search is None:
        total = len(analyses)
        start = (page - 1) * per_page
        items = []
        for analysis in analyses[start : start + per_page]:
            documents, extracted_data = _fetch_analysis_enrichment(analysis)
            items.append(_build_analysis_list_item(analysis, documents, extracted_data))
        return items, total

    # Search inspects document filenames and extracted data, which live outside the
    # analysis item, so every candidate has to be enriched before we can filter.
    items = []
    for analysis in analyses:
        documents, extracted_data = _fetch_analysis_enrichment(analysis)
        analysis_id = str(analysis.get("analysis_id"))
        primary_document_name = next(
            (document.get("filename") for document in documents if document.get("is_primary")),
            None,
        )
        haystack = " ".join(
            str(value).lower()
            for value in (primary_document_name, extracted_data, analysis_id)
            if value
        )
        if normalized_search not in haystack:
            continue
        items.append(_build_analysis_list_item(analysis, documents, extracted_data))

    total = len(items)
    start = (page - 1) * per_page
    return items[start : start + per_page], total


def create_analysis_with_documents_cosmos(
    *,
    user_id: str,
    user_name: str,
    files: list[IncomingUploadFile],
    primary_file_index: int,
) -> CosmosAnalysisResult:
    if len(files) == 0:
        raise ValueError("NO_FILES")
    if len(files) > MAX_FILES:
        raise ValueError("TOO_MANY_FILES")

    if len(files) == 1:
        primary_file_index = 0
    if primary_file_index < 0 or primary_file_index >= len(files):
        raise ValueError("MISSING_PRIMARY")

    analysis_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    analysis = {
        "id": _analysis_item_id(analysis_id),
        "type": "analysis",
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "created_by": user_id,
        "created_by_name": user_name,
        "status": "draft",
        "current_stage": CurrentStage.QUEUED.value,
        "progress_percentage": 0,
        "current_version_id": None,
        "correlation_id": str(uuid4()),
        "cancellation_requested": False,
        "error_message": None,
        "started_at": None,
        "timeout_at": None,
        "timeout_warning_at": None,
        "extraction_metadata": {},
        "created_at": now,
        "updated_at": now,
    }

    blob_storage = _build_blob_storage()
    uploaded_blob_names: list[str] = []
    warnings: list[DocumentWarning] = []
    documents: list[dict] = []

    try:
        for index, incoming_file in enumerate(files):
            safe_name = _sanitize_filename(incoming_file.filename)
            page_count, warning = _validate_pdf_or_raise(safe_name, incoming_file.content)
            if warning:
                warnings.append(warning)

            blob_name = f"{analysis_id}/{uuid4()}-{safe_name}"
            blob_storage.upload(blob_name, incoming_file.content)
            uploaded_blob_names.append(blob_name)

            doc_id = str(uuid4())
            document = {
                "id": f"document::{doc_id}",
                "type": "document",
                "partition_key": analysis_id,
                "analysis_id": analysis_id,
                "document_id": doc_id,
                "filename": safe_name,
                "blob_name": blob_name,
                "file_size_bytes": len(incoming_file.content),
                "page_count": int(page_count),
                "is_primary": index == primary_file_index,
                "sha256_hash": sha256(incoming_file.content).hexdigest(),
                "content_hash": calculate_content_hash(incoming_file.content),
                "created_by": user_id,
                "uploaded_at": now,
                "deleted": False,
            }
            documents.append(document)

        container = get_cosmos_container()
        container.upsert_item(analysis)
        for document in documents:
            container.upsert_item(document)

        return CosmosAnalysisResult(analysis=analysis, documents=documents, warnings=warnings)
    except Exception:
        for blob_name in uploaded_blob_names:
            blob_storage.delete(blob_name)
        raise


_DUPLICATE_ELIGIBLE_STATUSES = {"completed", "analyzing", "analyzed"}


def _check_duplicate_document_cosmos(
    content_hash: str,
    *,
    exclude_analysis_id: str,
    user_id: str,
) -> dict | None:
    container = get_cosmos_container()
    query = (
        "SELECT * FROM c WHERE c.type = 'document' "
        "AND c.content_hash = @content_hash "
        "AND c.created_by = @user_id "
        "AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
    )
    parameters = [
        {"name": "@content_hash", "value": content_hash},
        {"name": "@user_id", "value": user_id},
    ]
    documents = list(
        container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)
    )

    candidates: list[tuple[dict, dict]] = []
    for document in documents:
        candidate_analysis_id = str(document.get("analysis_id"))
        if candidate_analysis_id == exclude_analysis_id:
            continue
        analysis = _load_analysis_or_none(candidate_analysis_id)
        if analysis is None or analysis.get("status") not in _DUPLICATE_ELIGIBLE_STATUSES:
            continue
        candidates.append((document, analysis))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[1].get("created_at") or "", reverse=True)
    document, analysis = candidates[0]

    return {
        "analysis_id": str(analysis.get("analysis_id")),
        "created_at": str(analysis.get("created_at")),
        "status": str(analysis.get("status")),
    }


def find_duplicates_for_analysis_cosmos(
    analysis_id: str,
    user_id: str,
    created_by_label: str,
) -> list[dict]:
    duplicates: list[dict] = []
    for document in _query_documents(analysis_id):
        content_hash = document.get("content_hash")
        if not content_hash:
            continue

        duplicate = _check_duplicate_document_cosmos(
            str(content_hash),
            exclude_analysis_id=analysis_id,
            user_id=user_id,
        )
        if duplicate is None:
            continue

        duplicates.append(
            {
                "document_id": str(document.get("document_id")),
                "filename": str(document.get("filename")),
                "existing_analysis_id": duplicate["analysis_id"],
                "created_at": duplicate["created_at"],
                "created_by": created_by_label,
                "status": duplicate["status"],
            }
        )

    return duplicates


def _soft_delete_documents_cosmos(analysis_id: str, document_ids: set[str]) -> None:
    if not document_ids:
        return
    container = get_cosmos_container()
    now = datetime.now(UTC).isoformat()
    for document in _query_documents(analysis_id, include_deleted=True):
        if str(document.get("document_id")) not in document_ids:
            continue
        document["deleted"] = True
        document["deleted_at"] = now
        container.upsert_item(document)


def start_analysis_cosmos(analysis_id: str, user_id: str) -> dict:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")

    if analysis.get("status") not in {"draft", "error"}:
        raise RuntimeError("ANALYSIS_ALREADY_STARTED")

    analysis["status"] = "queued"
    analysis["current_stage"] = CurrentStage.QUEUED.value
    analysis["progress_percentage"] = 0
    analysis["cancellation_requested"] = False
    analysis["error_message"] = None
    metadata = analysis.get("extraction_metadata") or {}
    metadata["stage_progress"] = "En cola"
    analysis["extraction_metadata"] = metadata
    _upsert_analysis(analysis, "analysis_queued")

    return {
        "id": analysis_id,
        "status": "queued",
        "message": "Análisis encolado exitosamente.",
    }


def start_analysis_with_duplicates_cosmos(
    analysis_id: str,
    user_id: str,
    *,
    created_by_label: str,
    decisions: list[dict],
) -> dict:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")
    if analysis.get("status") not in {"draft", "error"}:
        raise RuntimeError("ANALYSIS_ALREADY_STARTED")

    duplicates = find_duplicates_for_analysis_cosmos(analysis_id, user_id, created_by_label)

    if duplicates:
        decision_map = {decision["document_id"]: decision["action"] for decision in decisions}
        unresolved = [item for item in duplicates if item["document_id"] not in decision_map]

        if unresolved:
            return {
                "id": analysis_id,
                "status": analysis.get("status", "draft"),
                "message": "Se detectaron documentos duplicados. Elegí qué hacer con cada uno.",
                "requires_resolution": True,
                "duplicates": duplicates,
                "redirect_analysis_id": None,
            }

        redirect_target: str | None = None
        cancelled_ids = {doc_id for doc_id, action in decision_map.items() if action == "cancel"}

        if cancelled_ids:
            _soft_delete_documents_cosmos(analysis_id, cancelled_ids)

        for duplicate in duplicates:
            if decision_map.get(duplicate["document_id"]) == "view_existing":
                redirect_target = duplicate["existing_analysis_id"]
                break

        remaining_docs = len(_query_documents(analysis_id))
        if remaining_docs == 0:
            return {
                "id": analysis_id,
                "status": analysis.get("status", "draft"),
                "message": "No quedan documentos para analizar. Podés volver al wizard y subir otros archivos.",
                "requires_resolution": False,
                "duplicates": [],
                "redirect_analysis_id": redirect_target,
            }

        if redirect_target:
            return {
                "id": analysis_id,
                "status": analysis.get("status", "draft"),
                "message": "Redirigiendo al análisis existente.",
                "requires_resolution": False,
                "duplicates": [],
                "redirect_analysis_id": redirect_target,
            }

    result = start_analysis_cosmos(analysis_id, user_id)
    return {
        "id": result["id"],
        "status": result["status"],
        "message": result["message"],
        "requires_resolution": False,
        "duplicates": [],
        "redirect_analysis_id": None,
    }


def get_analysis_detail_cosmos(analysis_id: str, user_id: str) -> dict:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")
    if not analysis.get("current_version_id"):
        raise ValueError("NO_VERSION_YET")

    latest_version = _get_latest_version(analysis_id)
    if latest_version is None:
        raise ValueError("NO_VERSION_YET")

    documents = _query_documents(analysis_id)

    return {
        "id": analysis_id,
        "created_at": _parse_dt(analysis.get("created_at")),
        "status": analysis.get("status", "draft"),
        "current_stage": analysis.get("current_stage", CurrentStage.QUEUED.value),
        "created_by": analysis.get("created_by"),
        "current_version": {
            "id": str(latest_version.get("version_id")),
            "version_number": int(latest_version.get("version_number", 0) or 0),
            "extracted_data": latest_version.get("extracted_data") or {},
            "conflicts": latest_version.get("conflicts"),
            "created_at": _parse_dt(latest_version.get("created_at")),
            "created_by": latest_version.get("created_by"),
        },
        "documents": [
            {
                "id": str(document.get("document_id")),
                "filename": str(document.get("filename")),
                "page_count": int(document.get("page_count") or 0),
                "file_size_bytes": int(document.get("file_size_bytes") or 0),
                "is_primary": bool(document.get("is_primary")),
            }
            for document in documents
        ],
    }


def get_analysis_status_cosmos(analysis_id: str, user_id: str) -> dict:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")

    latest_version = _get_latest_version(analysis_id) if analysis.get("current_version_id") else None
    metadata = analysis.get("extraction_metadata") or {}
    return {
        "id": analysis_id,
        "status": analysis.get("status", "draft"),
        "current_stage": analysis.get("current_stage", CurrentStage.QUEUED.value),
        "stage_progress": metadata.get("stage_progress"),
        "progress_percentage": int(analysis.get("progress_percentage", 0) or 0),
        "started_at": _parse_dt(analysis.get("started_at")),
        "timeout_at": _parse_dt(analysis.get("timeout_at")),
        "timeout_warning_at": _parse_dt(analysis.get("timeout_warning_at")),
        "error_message": analysis.get("error_message"),
        "extracted_data": (latest_version or {}).get("extracted_data"),
        "conflicts": (latest_version or {}).get("conflicts"),
    }


def cancel_analysis_cosmos(analysis_id: str, user_id: str) -> dict:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")

    analysis["cancellation_requested"] = True
    if analysis.get("status") not in {"analyzed", "error", "cancelled"}:
        analysis["status"] = "cancelled"
        analysis["current_stage"] = CurrentStage.COMPLETED.value
        analysis["progress_percentage"] = max(int(analysis.get("progress_percentage", 0) or 0), 95)
        analysis["error_message"] = "El analisis fue cancelado por el usuario"

    _upsert_analysis(analysis, "analysis_cancelled")
    return get_analysis_status_cosmos(analysis_id, user_id)


def extract_and_index_cosmos(analysis_id: str) -> None:
    analysis = _load_analysis_or_none(analysis_id)
    if analysis is None:
        logger.error("analysis_not_found", analysis_id=analysis_id)
        return

    correlation_id = analysis.get("correlation_id")
    documents = _query_documents(analysis_id)
    blob_storage = _build_blob_storage()

    if not documents:
        analysis["status"] = "error"
        analysis["current_stage"] = CurrentStage.COMPLETED.value
        analysis["error_message"] = "No se pudo procesar el documento. Intenta nuevamente"
        _upsert_analysis(analysis, "analysis_error")
        return

    total_pages = sum(int(document.get("page_count") or 0) for document in documents)
    timeout_minutes = calculate_timeout_minutes(total_pages)
    now = datetime.now(UTC)
    timeout_at = now + timedelta(minutes=timeout_minutes)
    analysis["started_at"] = now.isoformat()
    analysis["timeout_at"] = timeout_at.isoformat()
    analysis["timeout_warning_at"] = (timeout_at - timedelta(minutes=2)).isoformat()
    analysis["status"] = "processing"
    analysis["error_message"] = None
    analysis["cancellation_requested"] = False
    metadata = analysis.get("extraction_metadata") or {}
    metadata["timeout_minutes"] = timeout_minutes
    analysis["extraction_metadata"] = metadata
    _upsert_analysis(analysis, "analysis_processing")

    try:
        all_chunks: list[dict] = []
        total_docs = len(documents)

        for index, document in enumerate(documents, start=1):
            refreshed = _load_analysis_or_none(analysis_id)
            if refreshed and refreshed.get("cancellation_requested"):
                refreshed["status"] = "cancelled"
                refreshed["current_stage"] = CurrentStage.COMPLETED.value
                refreshed["error_message"] = "El analisis fue cancelado por el usuario"
                _upsert_analysis(refreshed, "analysis_cancelled")
                return

            analysis["current_stage"] = CurrentStage.EXTRACTING_TEXT.value
            analysis["progress_percentage"] = min(100, max(int(analysis.get("progress_percentage") or 0), int((index / total_docs) * 20)))
            metadata = analysis.get("extraction_metadata") or {}
            metadata["stage_progress"] = build_stage_progress(CurrentStage.EXTRACTING_TEXT, done=index, total=total_docs)
            analysis["extraction_metadata"] = metadata
            _upsert_analysis(analysis, "analysis_processing")

            blob_url = blob_storage.generate_download_url(str(document["blob_name"]))
            pages = extract_text(blob_url, str(document["document_id"]), str(correlation_id))
            chunks = create_chunks(pages, str(document["document_id"]), str(correlation_id))
            all_chunks.extend(chunks)

        analysis["current_stage"] = CurrentStage.INDEXING.value
        analysis["progress_percentage"] = max(int(analysis.get("progress_percentage") or 0), 30)
        metadata = analysis.get("extraction_metadata") or {}
        metadata["stage_progress"] = build_stage_progress(CurrentStage.INDEXING)
        analysis["extraction_metadata"] = metadata
        _upsert_analysis(analysis, "analysis_processing")

        chunks_with_embeddings = generate_embeddings(all_chunks, str(correlation_id))
        upload_chunks(chunks_with_embeddings, analysis_id, str(correlation_id))

        analysis["current_stage"] = CurrentStage.ANALYZING.value
        analysis["progress_percentage"] = max(int(analysis.get("progress_percentage") or 0), 50)
        metadata = analysis.get("extraction_metadata") or {}
        metadata["stage_progress"] = build_stage_progress(CurrentStage.ANALYZING, done=0, total=_TOTAL_CATEGORIES)
        analysis["extraction_metadata"] = metadata
        _upsert_analysis(analysis, "analysis_processing")

        result = graph.invoke(
            {
                "analysis_id": analysis_id,
                "correlation_id": str(correlation_id),
                "created_by": str(analysis.get("created_by")),
                "max_concurrency": 4,
                "extraction_metadata": {},
            },
            config={"max_concurrency": 4},
        )

        extracted_data = result.get("extracted_data", {})
        conflicts = result.get("conflicts", [])
        runtime_metadata = result.get("extraction_metadata", {})
        runtime_metadata["cost"] = _compute_cost(runtime_metadata)
        runtime_metadata["stage_progress"] = build_stage_progress(CurrentStage.COMPLETED)

        current_version_number = 0
        latest = _get_latest_version(analysis_id)
        if latest is not None:
            current_version_number = int(latest.get("version_number", 0) or 0)
        version_number = current_version_number + 1
        version_id = str(uuid4())

        version_item = {
            "id": f"version::{version_id}",
            "type": "analysis_version",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "version_id": version_id,
            "version_number": version_number,
            "created_by": analysis.get("created_by"),
            "created_at": datetime.now(UTC).isoformat(),
            "extracted_data": extracted_data,
            "conflicts": conflicts,
        }
        get_cosmos_container().upsert_item(version_item)

        analysis["current_version_id"] = version_id
        analysis["status"] = "analyzed"
        analysis["current_stage"] = CurrentStage.COMPLETED.value
        analysis["progress_percentage"] = 100
        analysis["error_message"] = None
        analysis["extraction_metadata"] = runtime_metadata
        _upsert_analysis(analysis, "analysis_version_created")
    except Exception:
        analysis["status"] = "error"
        analysis["current_stage"] = CurrentStage.COMPLETED.value
        analysis["error_message"] = "No se pudo procesar el documento. Intenta nuevamente"
        _upsert_analysis(analysis, "analysis_error")
        raise
