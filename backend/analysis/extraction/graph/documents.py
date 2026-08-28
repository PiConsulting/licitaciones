"""Carga de los documentos de un analisis y su etiquetado para citas (nombre visible, primario/anexo)."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _cleanup_temp_highlights(analysis_id: str) -> None:
    """Limpia archivos temporales de highlights descargados desde Azure."""
    try:
        from pathlib import Path
        import shutil
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / f"highlights-{analysis_id}"
        if not temp_dir.exists():
            logger.debug(
                "temp_highlights_already_clean",
                analysis_id=analysis_id,
                temp_dir=str(temp_dir),
            )
            return
        total_size = sum(f.stat().st_size for f in temp_dir.rglob("*") if f.is_file())
        file_count = sum(1 for _ in temp_dir.rglob("*") if _.is_file())

        shutil.rmtree(temp_dir)
        logger.info(
            "temp_highlights_cleaned",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            files_removed=file_count,
            bytes_freed=total_size,
        )
    except PermissionError as exc:
        logger.error(
            "temp_highlights_cleanup_permission_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            action_required="Check /tmp permissions and disk space",
        )
    except OSError as exc:
        logger.error(
            "temp_highlights_cleanup_os_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            action_required="Check disk space and filesystem health",
        )
    except Exception as exc:
        logger.error(
            "temp_highlights_cleanup_unexpected_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            error_type=type(exc).__name__,
            action_required="Investigate cleanup failure - /tmp may be filling up",
            exc_info=True,
        )


def _fetch_analysis_documents(analysis_id: str, db_session: Any) -> list[Any]:
    """Los documentos de un análisis, desde PostgreSQL."""
    if db_session is not None:
        from documents.models import Document

        return (
            db_session.query(Document)
            .filter(Document.analysis_id == analysis_id, Document.deleted_at.is_(None))
            .all()
        )

    from infra.config import get_settings

    settings = get_settings()
    if settings.is_production:
        logger.error(
            "build_document_mapping_failed_no_session",
            analysis_id=analysis_id,
            reason="db_session is None in production context",
        )
        raise RuntimeError(
            f"Cannot build document mapping for analysis {analysis_id}: "
            "db_session is required in production for highlight computation"
        )
    logger.warning(
        "build_document_mapping_skipped",
        analysis_id=analysis_id,
        reason="db_session not available (test context)",
    )
    return []


def _build_document_labels(analysis_id: str, db_session: Any) -> dict[str, dict[str, Any]]:
    """Mapeo `document_id -> {nombre, es_principal}` para el prompt (CTX-05)."""

    try:
        documents = _fetch_analysis_documents(analysis_id, db_session)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "document_labels_no_disponibles",
            analysis_id=analysis_id,
            error=str(exc),
            impact="el prompt identifica los documentos por UUID, como antes de CTX-05",
        )
        return {}

    etiquetas: dict[str, dict[str, Any]] = {}
    for documento in documents:
        document_id = str(getattr(documento, "id", "") or "")
        if not document_id:
            continue
        etiquetas[document_id] = {
            "nombre": str(getattr(documento, "filename", "") or "").strip(),
            "es_principal": bool(getattr(documento, "is_primary", False)),
        }

    principales = [doc_id for doc_id, datos in etiquetas.items() if datos["es_principal"]]
    if etiquetas and not principales:
        logger.warning(
            "document_labels_sin_principal",
            analysis_id=analysis_id,
            documentos=len(etiquetas),
        )
    elif len(principales) > 1:
        logger.warning(
            "document_labels_varios_principales",
            analysis_id=analysis_id,
            principales=len(principales),
        )

    logger.info(
        "document_labels_built",
        analysis_id=analysis_id,
        documentos=len(etiquetas),
        con_principal=bool(principales),
    )
    return etiquetas


def _stampar_nombre_de_documento(nodo: Any, etiquetas: dict[str, dict[str, Any]]) -> None:
    """escribe `filename`/`is_primary` en cada referencia a una fuente."""
    if not etiquetas:
        return

    if isinstance(nodo, dict):
        if "document_id" in nodo and "citation" in nodo:
            datos = etiquetas.get(str(nodo.get("document_id") or ""))
            if isinstance(datos, dict):
                nodo["filename"] = str(datos.get("nombre") or "") or None
                nodo["is_primary"] = bool(datos.get("es_principal"))
        for valor in nodo.values():
            _stampar_nombre_de_documento(valor, etiquetas)
    elif isinstance(nodo, list):
        for valor in nodo:
            _stampar_nombre_de_documento(valor, etiquetas)


def _build_document_mapping(analysis_id: str, db_session: Any) -> dict[str, str]:
    """Construye mapeo document_id → ruta absoluta del PDF en blob storage."""
    documents = _fetch_analysis_documents(analysis_id, db_session)
    if not documents:
        return {}

    from infra.config import get_settings

    settings = get_settings()
    try:
        from infra.adapters.azure_blob_storage import AzureBlobStorageAdapter

        blob_storage = AzureBlobStorageAdapter(
            settings.azure_blob_connection_string,
            settings.azure_blob_container_name,
        )

        mapping = {}
        if hasattr(blob_storage, "root"):
            for doc in documents:
                blob_path = blob_storage.root / doc.blob_name
                if blob_path.exists():
                    mapping[doc.id] = str(blob_path)
                else:
                    logger.warning(
                        "document_blob_not_found",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        blob_name=doc.blob_name,
                    )
        elif hasattr(blob_storage, "download_to_temp"):
            from pathlib import Path
            import tempfile

            temp_dir = Path(tempfile.gettempdir()) / f"highlights-{analysis_id}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            for doc in documents:
                temp_path = temp_dir / f"{doc.id}.pdf"
                try:
                    blob_storage.download_to_temp(doc.blob_name, str(temp_path))
                    mapping[doc.id] = str(temp_path)
                    logger.info(
                        "document_downloaded_for_highlights",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        temp_path=str(temp_path),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "document_download_failed",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        blob_name=doc.blob_name,
                        error=str(exc),
                    )

        else:
            logger.warning(
                "build_document_mapping_unsupported_storage",
                analysis_id=analysis_id,
                storage_type=type(blob_storage).__name__,
            )

        logger.info(
            "build_document_mapping_completed",
            analysis_id=analysis_id,
            documents_mapped=len(mapping),
        )
        return mapping

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "build_document_mapping_failed",
            analysis_id=analysis_id,
            error=str(exc),
        )
        return {}
