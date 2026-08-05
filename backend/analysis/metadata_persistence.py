from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import datetime as dt_parse
from typing import Protocol

import structlog

from analysis.models import Analysis, AnalysisVersion
from documents.models import Document
from shared.config import Settings, get_settings
from shared.security import sanitize_error_message

logger = structlog.get_logger(__name__)


class AnalysisMetadataSink(Protocol):
    def persist(
        self,
        *,
        analysis: Analysis,
        documents: list[Document],
        versions: list[AnalysisVersion],
        event: str,
    ) -> None: ...


class SqlMetadataSink:
    def persist(
        self,
        *,
        analysis: Analysis,
        documents: list[Document],
        versions: list[AnalysisVersion],
        event: str,
    ) -> None:
        return


class CosmosMetadataSink:
    def __init__(self, *, endpoint: str, key: str, database: str, container: str) -> None:
        self._endpoint = endpoint
        self._key = key
        self._database = database
        self._container = container

    def _get_container_client(self):
        from azure.cosmos import CosmosClient  # type: ignore[import-not-found]

        client = CosmosClient(url=self._endpoint, credential=self._key)
        return client.get_database_client(self._database).get_container_client(self._container)

    @staticmethod
    def _request_charge(response: object) -> float:
        get_headers = getattr(response, "get_response_headers", None)
        if callable(get_headers):
            headers = get_headers() or {}
            try:
                return float(headers.get("x-ms-request-charge", 0.0))
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def persist(
        self,
        *,
        analysis: Analysis,
        documents: list[Document],
        versions: list[AnalysisVersion],
        event: str,
    ) -> None:
        container = self._get_container_client()
        timestamp = datetime.now(UTC).isoformat()
        partition_key = str(analysis.id)
        total_ru = 0.0

        analysis_item = {
            "id": f"analysis::{analysis.id}",
            "type": "analysis",
            "partition_key": partition_key,
            "analysis_id": str(analysis.id),
            "status": analysis.status,
            "current_stage": analysis.current_stage,
            "progress_percentage": int(analysis.progress_percentage or 0),
            "current_version_id": str(analysis.current_version_id) if analysis.current_version_id else None,
            "correlation_id": str(analysis.correlation_id),
            "created_by": str(analysis.created_by),
            "extraction_metadata": analysis.extraction_metadata or {},
            "event": event,
            "started_at": analysis.started_at.isoformat() if analysis.started_at else None,
            "timeout_at": analysis.timeout_at.isoformat() if analysis.timeout_at else None,
            "timeout_warning_at": analysis.timeout_warning_at.isoformat() if analysis.timeout_warning_at else None,
            "error_message": analysis.error_message,
            "updated_at": timestamp,
        }
        total_ru += self._request_charge(container.upsert_item(analysis_item))

        for document in documents:
            total_ru += self._request_charge(
                container.upsert_item(
                    {
                        "id": f"document::{document.id}",
                        "type": "document",
                        "partition_key": partition_key,
                        "analysis_id": str(analysis.id),
                        "document_id": str(document.id),
                        "filename": document.filename,
                        "blob_name": document.blob_name,
                        "is_primary": bool(document.is_primary),
                        "page_count": int(document.page_count or 0),
                        "deleted": document.deleted_at is not None,
                        "event": event,
                        "updated_at": timestamp,
                    }
                )
            )

        for version in versions:
            total_ru += self._request_charge(
                container.upsert_item(
                    {
                        "id": f"version::{version.id}",
                        "type": "analysis_version",
                        "partition_key": partition_key,
                        "analysis_id": str(analysis.id),
                        "version_id": str(version.id),
                        "version_number": int(version.version_number),
                        "created_by": str(version.created_by) if version.created_by else None,
                        "extracted_data": version.extracted_data,
                        "conflicts": version.conflicts,
                        "event": event,
                        "updated_at": timestamp,
                    }
                )
            )

        logger.info(
            "cosmos_metadata_persisted",
            analysis_id=str(analysis.id),
            persistence_event=event,
            item_count=1 + len(documents) + len(versions),
            request_charge_ru=round(total_ru, 4),
        )


@dataclass
class DualWriteMetadataSink:
    primary: AnalysisMetadataSink
    secondary: AnalysisMetadataSink

    def persist(
        self,
        *,
        analysis: Analysis,
        documents: list[Document],
        versions: list[AnalysisVersion],
        event: str,
    ) -> None:
        self.primary.persist(analysis=analysis, documents=documents, versions=versions, event=event)
        self.secondary.persist(analysis=analysis, documents=documents, versions=versions, event=event)


def build_metadata_sink(settings: Settings | None = None) -> AnalysisMetadataSink:
    settings = settings or get_settings()
    mode = settings.persistence_mode_normalized()
    if mode == "sql":
        return SqlMetadataSink()

    cosmos_sink = CosmosMetadataSink(
        endpoint=settings.cosmos_endpoint,
        key=settings.cosmos_key,
        database=settings.cosmos_database,
        container=settings.cosmos_container,
    )
    if mode in {"cosmos", "cosmos_temporal", "cosmos_only"}:
        return cosmos_sink
    return DualWriteMetadataSink(primary=SqlMetadataSink(), secondary=cosmos_sink)


def persist_analysis_metadata(
    *,
    analysis: Analysis,
    documents: list[Document] | None = None,
    versions: list[AnalysisVersion] | None = None,
    event: str,
) -> None:
    settings = get_settings()
    sink = build_metadata_sink(settings)
    docs = documents or []
    version_list = versions or []

    try:
        sink.persist(analysis=analysis, documents=docs, versions=version_list, event=event)
    except Exception as exc:
        logger.error(
            "metadata_persistence_failed",
            analysis_id=str(analysis.id),
            correlation_id=str(analysis.correlation_id),
            persistence_mode=settings.persistence_mode,
            error=sanitize_error_message(str(exc)),
        )
        if settings.is_production and settings.persistence_mode_normalized() in {
            "cosmos",
            "dual_write",
            "cosmos_temporal",
            "cosmos_only",
        }:
            raise RuntimeError("No se pudo persistir metadata en Cosmos para modo cloud") from exc


def read_runtime_analysis_from_cosmos(analysis_id: str, settings: Settings | None = None) -> dict | None:
    settings = settings or get_settings()
    sink = CosmosMetadataSink(
        endpoint=settings.cosmos_endpoint,
        key=settings.cosmos_key,
        database=settings.cosmos_database,
        container=settings.cosmos_container,
    )
    container = sink._get_container_client()

    analysis_item = None
    item_id = f"analysis::{analysis_id}"
    for partition_key in [analysis_id, item_id]:
        try:
            analysis_item = container.read_item(item=item_id, partition_key=partition_key)
            break
        except Exception:  # noqa: BLE001
            logger.debug(
                "cosmos_runtime_read_fallback_failed",
                analysis_id=analysis_id,
                attempted_partition_key=partition_key,
            )
            continue

    if analysis_item is None:
        rows = list(
            container.query_items(
                query="SELECT TOP 1 * FROM c WHERE c.type = 'analysis' AND c.analysis_id = @analysis_id",
                parameters=[{"name": "@analysis_id", "value": analysis_id}],
                enable_cross_partition_query=True,
            )
        )
        if rows:
            analysis_item = rows[0]

    if analysis_item is None:
        return None

    latest_version = None
    try:
        versions = list(
            container.query_items(
                query="SELECT * FROM c WHERE c.type = 'analysis_version' AND c.analysis_id = @analysis_id ORDER BY c.version_number DESC",
                parameters=[{"name": "@analysis_id", "value": analysis_id}],
                enable_cross_partition_query=True,
            )
        )
        if versions:
            latest_version = versions[0]
    except Exception:  # noqa: BLE001
        latest_version = None

    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return dt_parse.fromisoformat(value)
        except ValueError:
            return None

    metadata = analysis_item.get("extraction_metadata") or {}
    return {
        "id": analysis_item.get("analysis_id", analysis_id),
        "status": analysis_item.get("status", "draft"),
        "current_stage": analysis_item.get("current_stage", "queued"),
        "stage_progress": metadata.get("stage_progress"),
        "progress_percentage": int(analysis_item.get("progress_percentage", 0) or 0),
        "started_at": _parse_dt(analysis_item.get("started_at")),
        "timeout_at": _parse_dt(analysis_item.get("timeout_at")),
        "timeout_warning_at": _parse_dt(analysis_item.get("timeout_warning_at")),
        "error_message": analysis_item.get("error_message"),
        "extracted_data": (latest_version or {}).get("extracted_data"),
        "conflicts": (latest_version or {}).get("conflicts"),
    }
