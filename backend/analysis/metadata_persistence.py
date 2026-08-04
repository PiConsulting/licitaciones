from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
        from azure.cosmos import CosmosClient

        client = CosmosClient(url=self._endpoint, credential=self._key)
        return client.get_database_client(self._database).get_container_client(self._container)

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

        analysis_item = {
            "id": f"analysis::{analysis.id}",
            "type": "analysis",
            "analysis_id": str(analysis.id),
            "status": analysis.status,
            "current_stage": analysis.current_stage,
            "progress_percentage": int(analysis.progress_percentage or 0),
            "current_version_id": str(analysis.current_version_id) if analysis.current_version_id else None,
            "correlation_id": str(analysis.correlation_id),
            "created_by": str(analysis.created_by),
            "extraction_metadata": analysis.extraction_metadata or {},
            "event": event,
            "updated_at": timestamp,
        }
        container.upsert_item(analysis_item)

        for document in documents:
            container.upsert_item(
                {
                    "id": f"document::{document.id}",
                    "type": "document",
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

        for version in versions:
            container.upsert_item(
                {
                    "id": f"version::{version.id}",
                    "type": "analysis_version",
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
    if mode == "cosmos":
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
        if settings.is_production and settings.persistence_mode_normalized() in {"cosmos", "dual_write"}:
            raise RuntimeError("No se pudo persistir metadata en Cosmos para modo cloud") from exc
