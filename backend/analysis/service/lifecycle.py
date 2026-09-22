"""Ciclo de vida de un analisis despues de creado: encolar extraccion, cancelar, eliminar (soft/hard)."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from copy import deepcopy

from fastapi import BackgroundTasks, HTTPException, status
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from analysis.extraction.extractors import (
    extractor_anexos_obligatorios,
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_eventos_temporales,
    extractor_garantias,
    extractor_identificacion_procedimiento,
    extractor_objeto_alcance,
    extractor_plazos,
    extractor_preview_criterios,
    extractor_requisitos_admisibilidad,
    extractor_riesgos,
)
from analysis.extraction.graph.nodes import merge_node, setup_node, synthesize_node
from analysis.extraction.runner import (
    _merge_conflicts,
    extract_categories_phase1,
)
from analysis.extraction.state import GraphState
from analysis.models import Analysis, CurrentStage
from analysis.progress import build_stage_progress
from analysis.service.cancellation import revert_or_mark_cancelled
from analysis.service.upload import _build_blob_storage
from documents.models import Document
from indexing.runner import TOTAL_PHASE1_NODES, extract_and_index_phase1, extract_and_index_phase2
from infra.adapters.pgvector_search import delete_analysis_chunks
from infra.config import get_settings
from infra.database import SessionLocal
from timeline.materializer import materialize_timeline_from_extraction

logger = logging.getLogger(__name__)

_PHASE1_CATEGORY_IDS = [
    "preview_criterios",
    "objeto_alcance",
    "identificacion_procedimiento",
    "requisitos_admisibilidad",
    "plazos_clave",
    "garantias",
]

# FIX (2026-09-18, rediseño de `riesgos`): movido de fase 1 a fase 2 -- ya no
# scanea chunks crudos, sintetiza desde garantias/plazos/requisitos (fase 1) +
# causales/criterios (fase 2, recién calculados en la misma fase).
_PHASE2_CATEGORY_IDS = [
    "causales_rechazo",
    "anexos_obligatorios",
    "criterios_evaluacion",
    "eventos_temporales",
    "plazos_relativos",
    "riesgos",
]

# `extractor_preview_criterios` no vuelve a llamar al LLM para estos 3 tipos
# de preview -- los PROYECTA leyendo `state["garantias"]`/`state["plazos"]`/
# `state["requisitos_admisibilidad"]` ya calculados (ver
# `analysis/extraction/extractors/preview_criterios.py`). Si `preview_criterios`
# se reanaliza solo (sin esas 3 categorías en el mismo batch), el grafo de una
# sola categoria arranca con un `GraphState` vacío y esos `state.get(...)`
# devuelven `[]`, así que la proyección da `not_found` para items que en
# realidad SÍ están extraídos y persistidos en la versión -- pisando el
# preview bueno que ya existía (bug reportado 2026-09-11: "mantenimiento de
# oferta" aparecía y desaparecía entre reanálisis sin que cambiara el pliego).
# `riesgos` salió de esta lista 2026-09-18: `multas_penalidades` (lo único que
# preview necesitaba de riesgos) pasó a extracción directa en
# `preview_criterios.txt` -- preview ya no depende de riesgos en absoluto.
_PREVIEW_CRITERIOS_SOURCE_STATE_KEYS = [
    "garantias",
    "plazos",
    "requisitos_admisibilidad",
]

# FIX (2026-09-18, mismo rediseño): `riesgos` ahora sintetiza desde estas 5
# categorías ya extraídas en vez de escanear chunks crudos -- si se reanaliza
# SOLO "riesgos" (mini-grafo aislado, ver `_build_single_category_graph`), hay
# que sembrar `initial_state` con lo ya persistido en la versión, igual que ya
# se hace arriba para `preview_criterios`. Sin esto, `extractor_riesgos`
# arrancaría con las 5 fuentes vacías y no tendría nada para sintetizar.
#
# Mapa (nombre del campo en `GraphState` -> clave con la que se persiste en
# `AnalysisVersion.extracted_data`): para garantias/plazos/requisitos_
# admisibilidad son el mismo string, pero `causales`/`criterios` (nombres de
# `state_field` en sus extractores) se persisten como `causales_rechazo`/
# `criterios_evaluacion` (ver `_CATEGORY_TO_DATA_KEYS` debajo) -- sembrar con
# el nombre equivocado dejaría `state["causales"]`/`state["criterios"]`
# siempre vacíos sin que ningún test lo notara si no se distingue esto.
_RIESGOS_SOURCE_STATE_KEYS: list[tuple[str, str]] = [
    ("garantias", "garantias"),
    ("plazos", "plazos"),
    ("requisitos_admisibilidad", "requisitos_admisibilidad"),
    ("causales", "causales_rechazo"),
    ("criterios", "criterios_evaluacion"),
]

_CATEGORY_TO_DATA_KEYS = {
    "preview_criterios": [
        "preview_criterios",
        "preview_criterios_extraction_status",
        "preview_criterios_narrative",
        "preview_criterios_confidence",
    ],
    "objeto_alcance": [
        "objeto_alcance",
        "objeto_alcance_extraction_status",
        "objeto_alcance_narrative",
        "objeto_alcance_confidence",
    ],
    "identificacion_procedimiento": [
        "identificacion_procedimiento",
        "identificacion_procedimiento_extraction_status",
        "identificacion_procedimiento_narrative",
        "datos_procedimiento",
        "datos_procedimiento_extraction_status",
        "datos_procedimiento_confidence",
    ],
    "requisitos_admisibilidad": [
        "requisitos_admisibilidad",
        "requisitos_admisibilidad_extraction_status",
        "requisitos_admisibilidad_narrative",
        "requisitos_admisibilidad_confidence",
    ],
    "plazos_clave": [
        "plazos_clave",
        "plazos_clave_extraction_status",
        "plazos_clave_narrative",
        "plazos_clave_confidence",
        "plazos",
        "plazos_extraction_status",
    ],
    "garantias": [
        "garantias",
        "garantias_extraction_status",
        "garantias_narrative",
        "garantias_confidence",
    ],
    "riesgos": [
        "riesgos",
        "riesgos_extraction_status",
        "riesgos_narrative",
        "riesgos_confidence",
    ],
    "causales_rechazo": [
        "causales_rechazo",
        "causales_rechazo_extraction_status",
        "causales_rechazo_narrative",
        "causales_rechazo_confidence",
        "causales_extraction_status",
    ],
    "anexos_obligatorios": [
        "anexos_obligatorios",
        "anexos_obligatorios_extraction_status",
        "anexos_obligatorios_narrative",
        "anexos_obligatorios_confidence",
    ],
    "criterios_evaluacion": [
        "criterios_evaluacion",
        "criterios_evaluacion_extraction_status",
        "criterios_evaluacion_narrative",
        "criterios_evaluacion_confidence",
    ],
    "eventos_temporales": [
        "eventos_temporales",
        "eventos_temporales_extraction_status",
        "plazos_relativos",
        "plazos_relativos_extraction_status",
    ],
    "plazos_relativos": [
        "plazos_relativos",
        "plazos_relativos_extraction_status",
        "eventos_temporales",
        "eventos_temporales_extraction_status",
    ],
}

_CATEGORY_EXTRACTOR_SPECS = {
    "preview_criterios": {
        "node": "extract_preview_criterios",
        "extractor": extractor_preview_criterios,
        "keys": _CATEGORY_TO_DATA_KEYS["preview_criterios"],
        "quality_key": "preview_criterios",
        "conflict_categories": {"preview_criterios"},
    },
    "objeto_alcance": {
        "node": "extract_objeto_alcance",
        "extractor": extractor_objeto_alcance,
        "keys": _CATEGORY_TO_DATA_KEYS["objeto_alcance"],
        "quality_key": "objeto_alcance",
        "conflict_categories": {"objeto_alcance"},
    },
    "identificacion_procedimiento": {
        "node": "extract_identificacion",
        "extractor": extractor_identificacion_procedimiento,
        "keys": _CATEGORY_TO_DATA_KEYS["identificacion_procedimiento"],
        "quality_key": "identificacion_procedimiento",
        "conflict_categories": {"identificacion_procedimiento"},
    },
    "requisitos_admisibilidad": {
        "node": "extract_requisitos",
        "extractor": extractor_requisitos_admisibilidad,
        "keys": _CATEGORY_TO_DATA_KEYS["requisitos_admisibilidad"],
        "quality_key": "requisitos_admisibilidad",
        "conflict_categories": {"requisitos_admisibilidad"},
    },
    "plazos_clave": {
        "node": "extract_plazos",
        "extractor": extractor_plazos,
        "keys": _CATEGORY_TO_DATA_KEYS["plazos_clave"],
        "quality_key": "plazos_clave",
        "conflict_categories": {"plazos_clave"},
    },
    "garantias": {
        "node": "extract_garantias",
        "extractor": extractor_garantias,
        "keys": _CATEGORY_TO_DATA_KEYS["garantias"],
        "quality_key": "garantias",
        "conflict_categories": {"garantias"},
    },
    "riesgos": {
        "node": "extract_riesgos",
        "extractor": extractor_riesgos,
        "keys": _CATEGORY_TO_DATA_KEYS["riesgos"],
        "quality_key": "riesgos",
        "conflict_categories": {"riesgos"},
    },
    "causales_rechazo": {
        "node": "extract_causales",
        "extractor": extractor_causales,
        "keys": _CATEGORY_TO_DATA_KEYS["causales_rechazo"],
        "quality_key": "causales_rechazo",
        "conflict_categories": {"causales_rechazo"},
    },
    "anexos_obligatorios": {
        "node": "extract_anexos",
        "extractor": extractor_anexos_obligatorios,
        "keys": _CATEGORY_TO_DATA_KEYS["anexos_obligatorios"],
        "quality_key": "anexos_obligatorios",
        "conflict_categories": {"anexos_obligatorios"},
    },
    "criterios_evaluacion": {
        "node": "extract_criterios",
        "extractor": extractor_criterios_evaluacion,
        "keys": _CATEGORY_TO_DATA_KEYS["criterios_evaluacion"],
        "quality_key": "criterios_evaluacion",
        "conflict_categories": {"criterios_evaluacion"},
    },
    "eventos_temporales": {
        "node": "extract_eventos_temporales",
        "extractor": extractor_eventos_temporales,
        "keys": _CATEGORY_TO_DATA_KEYS["eventos_temporales"],
        "quality_key": None,
        "conflict_categories": {"eventos_temporales", "plazos_relativos"},
        "is_timeline": True,
    },
    "plazos_relativos": {
        "node": "extract_eventos_temporales",
        "extractor": extractor_eventos_temporales,
        "keys": _CATEGORY_TO_DATA_KEYS["plazos_relativos"],
        "quality_key": None,
        "conflict_categories": {"eventos_temporales", "plazos_relativos"},
        "is_timeline": True,
    },
}


def _build_single_category_graph(node_name: str, extractor_fn):
    builder = StateGraph(GraphState)
    builder.add_node("setup", setup_node)
    builder.add_node(node_name, extractor_fn)
    builder.add_node("merge", merge_node)
    builder.add_node("synthesize", synthesize_node)
    builder.set_entry_point("setup")
    builder.add_edge("setup", node_name)
    builder.add_edge(node_name, "merge")
    builder.add_edge("merge", "synthesize")
    builder.add_edge("synthesize", END)
    return builder.compile()


def _normalize_selected_categories(selected_categories: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for category in selected_categories:
        if not category:
            continue
        effective = "eventos_temporales" if category == "plazos_relativos" else category
        if effective in seen:
            continue
        seen.add(effective)
        normalized.append(effective)
    return normalized


def _run_phase1_reanalysis_without_reindex(analysis_id: str) -> None:
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None:
            return
        extract_categories_phase1(db, analysis, total_nodes=TOTAL_PHASE1_NODES)
    finally:
        db.close()


def _run_selected_categories_reanalysis(analysis_id: str, selected_categories: list[str]) -> None:
    normalized_categories = _normalize_selected_categories(selected_categories)
    if not normalized_categories:
        return

    settings = get_settings()
    max_concurrency = int(settings.extraction_max_concurrency or 4)

    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None or not analysis.current_version_id:
            return

        version = next(
            (item for item in analysis.versions if item.id == analysis.current_version_id),
            None,
        )
        if version is None:
            return

        analysis.status = "processing"
        analysis.current_stage = CurrentStage.ANALYZING.value
        analysis.error_message = None
        analysis.updated_at = datetime.now(UTC)
        analysis.extraction_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": build_stage_progress(
                CurrentStage.ANALYZING,
                done=0,
                total=len(normalized_categories),
                analyzing_label="categorias seleccionadas",
            ),
        }
        db.commit()

        for index, category in enumerate(normalized_categories, start=1):
            db.refresh(analysis)
            if analysis.cancellation_requested:
                revert_or_mark_cancelled(analysis, db)
                db.commit()
                return

            spec = _CATEGORY_EXTRACTOR_SPECS.get(category)
            if spec is None:
                continue

            graph = _build_single_category_graph(spec["node"], spec["extractor"])
            initial_state: GraphState = {
                "analysis_id": analysis.id,
                "correlation_id": analysis.correlation_id,
                "created_by": analysis.created_by,
                "max_concurrency": max_concurrency,
                "extraction_metadata": {},
                "db_session": db,
            }
            if category == "preview_criterios":
                current_data = version.extracted_data or {}
                for source_key in _PREVIEW_CRITERIOS_SOURCE_STATE_KEYS:
                    initial_state[source_key] = current_data.get(source_key, [])
            if category == "riesgos":
                current_data = version.extracted_data or {}
                for state_key, data_key in _RIESGOS_SOURCE_STATE_KEYS:
                    initial_state[state_key] = current_data.get(data_key, [])
            result = graph.invoke(initial_state, config={"max_concurrency": 1})

            fresh_data = dict(result.get("extracted_data") or {})
            merged_data = dict(version.extracted_data or {})
            for key in spec["keys"]:
                if key in fresh_data:
                    merged_data[key] = fresh_data[key]

            quality_key = spec.get("quality_key")
            if quality_key:
                merged_quality = dict(merged_data.get("calidad_por_categoria") or {})
                fresh_quality = dict(fresh_data.get("calidad_por_categoria") or {})
                if quality_key in fresh_quality:
                    merged_quality[quality_key] = fresh_quality[quality_key]
                if merged_quality:
                    merged_data["calidad_por_categoria"] = merged_quality

            version.extracted_data = merged_data

            fresh_conflicts = [
                conflict
                for conflict in (result.get("conflicts") or [])
                if conflict.get("category") in spec["conflict_categories"]
            ]
            kept_conflicts = [
                conflict
                for conflict in list(version.conflicts or [])
                if conflict.get("category") not in spec["conflict_categories"]
            ]
            version.conflicts = _merge_conflicts(kept_conflicts, fresh_conflicts)

            if spec.get("is_timeline"):
                timeline_eventos = fresh_data.get(
                    "eventos_temporales",
                    result.get("eventos_temporales", []),
                )
                timeline_plazos = fresh_data.get(
                    "plazos_relativos",
                    result.get("plazos_relativos", []),
                )
                materialize_timeline_from_extraction(
                    db,
                    analysis_id=analysis.id,
                    created_by=analysis.created_by,
                    eventos_temporales=timeline_eventos,
                    plazos_relativos=timeline_plazos,
                )

            metadata = dict(analysis.extraction_metadata or {})
            token_usage = dict(metadata.get("token_usage") or {})
            token_usage.update(
                dict((result.get("extraction_metadata") or {}).get("token_usage") or {})
            )
            metadata["token_usage"] = token_usage
            metadata["stage_progress"] = build_stage_progress(
                CurrentStage.ANALYZING,
                done=index,
                total=len(normalized_categories),
                analyzing_label="categorias seleccionadas",
            )
            metadata["reanalysis_completed_as"] = "selected_categories_only"
            analysis.extraction_metadata = metadata
            analysis.progress_percentage = min(95, max(analysis.progress_percentage or 0, 30 + int((index / len(normalized_categories)) * 50)))
            analysis.updated_at = datetime.now(UTC)
            db.commit()

        db.refresh(analysis)
        if analysis.cancellation_requested:
            revert_or_mark_cancelled(analysis, db)
            db.commit()
            return

        analysis.status = "analyzed"
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.progress_percentage = 100
        analysis.error_message = None
        analysis.updated_at = datetime.now(UTC)
        analysis.extraction_metadata = {
            **(analysis.extraction_metadata or {}),
            "stage_progress": build_stage_progress(CurrentStage.COMPLETED),
        }
        db.commit()
    finally:
        db.close()


def _merge_phase1_into_latest_version(analysis_id: str, source_version_id: str | None) -> None:
    """Completa reanálisis phase1 como versión FULL heredando claves no recalculadas."""
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None or not analysis.current_version_id:
            return

        if analysis.cancellation_requested:
            revert_or_mark_cancelled(analysis, db)
            db.commit()
            return

        latest_version = next(
            (version for version in analysis.versions if version.id == analysis.current_version_id),
            None,
        )
        if latest_version is None:
            return

        source_version = None
        if source_version_id:
            source_version = next((version for version in analysis.versions if version.id == source_version_id), None)

        if source_version is not None:
            merged_data = dict(source_version.extracted_data or {})
            merged_data.update(latest_version.extracted_data or {})
            latest_version.extracted_data = merged_data
            latest_version.conflicts = _merge_conflicts(
                source_version.conflicts,
                latest_version.conflicts,
            )

        # Reanálisis de fase 1 debe dejar una versión utilizable por defecto.
        analysis.status = "analyzed"
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.progress_percentage = 100
        analysis.error_message = None
        analysis.updated_at = datetime.now(UTC)
        metadata = dict(analysis.extraction_metadata or {})
        metadata["stage_progress"] = "Completado"
        metadata["reanalysis_completed_as"] = "phase1_full_version"
        analysis.extraction_metadata = metadata
        db.commit()
    finally:
        db.close()


def _clone_current_version_for_phase2_reanalysis(analysis_id: str) -> str | None:
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None or not analysis.current_version_id:
            return None

        source_version = next(
            (version for version in analysis.versions if version.id == analysis.current_version_id),
            None,
        )
        if source_version is None:
            return None

        max_number = max((int(version.version_number) for version in analysis.versions), default=0)
        from analysis.models import AnalysisVersion

        clone = AnalysisVersion(
            analysis_id=analysis.id,
            version_number=max_number + 1,
            extracted_data=deepcopy(source_version.extracted_data or {}),
            conflicts=deepcopy(source_version.conflicts or []),
            created_by=analysis.created_by,
        )
        db.add(clone)
        db.flush()

        analysis.current_version_id = clone.id
        analysis.updated_at = datetime.now(UTC)
        db.commit()
        return clone.id
    finally:
        db.close()


def _apply_selected_categories_only(
    analysis_id: str,
    selected_categories: list[str],
    source_version_id: str | None,
) -> None:
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None or not analysis.current_version_id or not source_version_id:
            return

        latest_version = next(
            (version for version in analysis.versions if version.id == analysis.current_version_id),
            None,
        )
        source_version = next((version for version in analysis.versions if version.id == source_version_id), None)
        if latest_version is None or source_version is None:
            return

        selected_set = {category for category in selected_categories if category}
        source_data = dict(source_version.extracted_data or {})
        fresh_data = dict(latest_version.extracted_data or {})
        merged = dict(source_data)

        for category in selected_set:
            for key in _CATEGORY_TO_DATA_KEYS.get(category, [category]):
                if key in fresh_data:
                    merged[key] = fresh_data[key]

        source_quality = dict(source_data.get("calidad_por_categoria") or {})
        fresh_quality = dict(fresh_data.get("calidad_por_categoria") or {})
        for category in selected_set:
            if category in fresh_quality:
                source_quality[category] = fresh_quality[category]
        if source_quality:
            merged["calidad_por_categoria"] = source_quality

        latest_version.extracted_data = merged

        source_conflicts = list(source_version.conflicts or [])
        fresh_conflicts = list(latest_version.conflicts or [])
        selected_conflicts = [
            conflict for conflict in fresh_conflicts if conflict.get("category") in selected_set
        ]
        kept_conflicts = [
            conflict for conflict in source_conflicts if conflict.get("category") not in selected_set
        ]
        latest_version.conflicts = _merge_conflicts(kept_conflicts, selected_conflicts)

        metadata = dict(analysis.extraction_metadata or {})
        metadata["reanalysis_type"] = "categories"
        metadata["reanalysis_categories"] = list(selected_categories)
        metadata["reanalysis_completed_as"] = "selected_categories_full_version"
        analysis.extraction_metadata = metadata
        analysis.status = "analyzed"
        analysis.current_stage = CurrentStage.COMPLETED.value
        analysis.progress_percentage = 100
        analysis.error_message = None
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _append_reanalysis_audit_event(
    analysis_id: str,
    *,
    reanalysis_type: str,
    categories: list[str],
    source_version_id: str | None,
    triggered_by: str | None,
    status_value: str,
    started_at: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None:
            return

        metadata = dict(analysis.extraction_metadata or {})
        history = list(metadata.get("reanalysis_history") or [])
        event_started_at = started_at or datetime.now(UTC).isoformat()
        history.append(
            {
                "at": datetime.now(UTC).isoformat(),
                "started_at": event_started_at,
                "analysis_id": analysis_id,
                "reanalysis_type": reanalysis_type,
                "categories": list(categories),
                "triggered_by": triggered_by,
                "status": status_value,
                "source_version_id": source_version_id,
                "target_version_id": analysis.current_version_id,
            }
        )
        metadata["reanalysis_history"] = history[-50:]
        analysis.extraction_metadata = metadata
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def validate_analysis_ownership(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = (
        db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    )
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ANALYSIS_NOT_FOUND", "message": "Análisis no encontrado"}},
        )

    if analysis.created_by != user_id:
        logger.warning(
            "Unauthorized access to analysis. user_id=%s analysis_id=%s owner_id=%s",
            user_id,
            analysis_id,
            analysis.created_by,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {"code": "FORBIDDEN", "message": "No tenés permisos para este análisis"}
            },
        )

    return analysis


def enqueue_analysis(background_tasks: BackgroundTasks, analysis_id: str) -> None:
    """Enqueue sync extraction/indexing in FastAPI background threadpool."""
    background_tasks.add_task(extract_and_index_phase1, analysis_id)


def enqueue_analysis_categories(background_tasks: BackgroundTasks, analysis_id: str) -> None:
    """Enqueue fase 2 (solo categorías restantes) en background."""
    background_tasks.add_task(extract_and_index_phase2, analysis_id)


def _run_reanalysis(analysis_id: str, reanalysis_type: str, categories: list[str]) -> None:
    """Dispatch mínimo para contrato de reanálisis (Story 24.1)."""
    source_version_id = None
    triggered_by = None
    started_at = None
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is not None:
            source_version_id = analysis.current_version_id
            triggered_by = analysis.created_by
            started_at = datetime.now(UTC).isoformat()
    finally:
        db.close()

    _append_reanalysis_audit_event(
        analysis_id,
        reanalysis_type=reanalysis_type,
        categories=categories,
        source_version_id=source_version_id,
        triggered_by=triggered_by,
        status_value="started",
        started_at=started_at,
    )

    if reanalysis_type == "all":
        extract_and_index_phase1(analysis_id)
        extract_and_index_phase2(analysis_id)
        _append_reanalysis_audit_event(
            analysis_id,
            reanalysis_type=reanalysis_type,
            categories=categories,
            source_version_id=source_version_id,
            triggered_by=triggered_by,
            status_value="completed",
            started_at=started_at,
        )
        return

    if reanalysis_type == "phase1":
        _run_phase1_reanalysis_without_reindex(analysis_id)
        _merge_phase1_into_latest_version(analysis_id, source_version_id)
        _append_reanalysis_audit_event(
            analysis_id,
            reanalysis_type=reanalysis_type,
            categories=categories,
            source_version_id=source_version_id,
            triggered_by=triggered_by,
            status_value="completed",
            started_at=started_at,
        )
        return

    if reanalysis_type == "phase2":
        clone_id = _clone_current_version_for_phase2_reanalysis(analysis_id)
        logger.info(
            "reanalysis_phase2_version_cloned",
            extra={"analysis_id": analysis_id, "cloned_version_id": clone_id},
        )
        extract_and_index_phase2(analysis_id)
        _append_reanalysis_audit_event(
            analysis_id,
            reanalysis_type=reanalysis_type,
            categories=categories,
            source_version_id=source_version_id,
            triggered_by=triggered_by,
            status_value="completed",
            started_at=started_at,
        )
        return

    if reanalysis_type == "categories":
        clone_id = _clone_current_version_for_phase2_reanalysis(analysis_id)
        logger.info(
            "reanalysis_categories_version_cloned",
            extra={"analysis_id": analysis_id, "cloned_version_id": clone_id},
        )
        _run_selected_categories_reanalysis(analysis_id, categories)
        _append_reanalysis_audit_event(
            analysis_id,
            reanalysis_type=reanalysis_type,
            categories=categories,
            source_version_id=source_version_id,
            triggered_by=triggered_by,
            status_value="completed",
            started_at=started_at,
        )
        return

    logger.info(
        "reanalysis_dispatch_phase2",
        extra={
            "analysis_id": analysis_id,
            "reanalysis_type": reanalysis_type,
            "categories": categories,
        },
    )
    extract_and_index_phase2(analysis_id)
    _append_reanalysis_audit_event(
        analysis_id,
        reanalysis_type=reanalysis_type,
        categories=categories,
        source_version_id=source_version_id,
        triggered_by=triggered_by,
        status_value="completed",
        started_at=started_at,
    )


def enqueue_reanalyze(
    background_tasks: BackgroundTasks,
    analysis_id: str,
    reanalysis_type: str,
    categories: list[str] | None = None,
) -> None:
    """Enqueue reanálisis con tipo y categorías objetivo."""
    background_tasks.add_task(
        _run_reanalysis,
        analysis_id,
        reanalysis_type,
        categories or [],
    )


def request_cancellation(db: Session, analysis_id: str, user_id: str) -> Analysis:
    analysis = (
        db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None)).first()
    )
    if analysis is None:
        raise ValueError("Analysis not found")

    if analysis.created_by != user_id:
        raise PermissionError("Only the owner can cancel this analysis")

    analysis.cancellation_requested = True
    # `en_revision` no es terminal: el usuario todavía puede continuar a fase 2.
    # Si hay un reanálisis en curso, cancelar descarta el intento y vuelve al
    # status/versión previos en vez de marcar todo el análisis "cancelled"
    # (ver `revert_or_mark_cancelled`).
    revert_or_mark_cancelled(analysis, db)

    db.commit()
    db.refresh(analysis)
    return analysis


def delete_analysis(db: Session, analysis_id: str, user_id: str) -> str:
    analysis = validate_analysis_ownership(db, analysis_id, user_id)
    current_status = analysis.status.lower()

    # `en_revision` no bloquea eliminación: ya terminó fase 1 y no hay trabajo activo.
    if current_status in {"queued", "analyzing", "processing"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "ANALYSIS_DELETE_NOT_ALLOWED",
                    "message": "No podés eliminar un análisis en curso",
                }
            },
        )

    if current_status == "error":
        blob_storage = _build_blob_storage()
        documents = db.query(Document).filter(Document.analysis_id == analysis.id).all()
        for document in documents:
            blob_storage.delete(document.blob_name)
        delete_analysis_chunks(analysis.id)
        db.delete(analysis)
        db.commit()
        return "hard"

    now = datetime.now(UTC)
    analysis.deleted_at = now
    (
        db.query(Document)
        .filter(Document.analysis_id == analysis.id, Document.deleted_at.is_(None))
        .update({Document.deleted_at: now}, synchronize_session=False)
    )
    db.commit()
    return "soft"


def run_analysis_stub(analysis_id: str) -> None:
    """STUB sync processor for Story 2.3 background execution."""
    db = SessionLocal()
    try:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
            .first()
        )
        if analysis is None:
            logger.error("[STUB] Analysis %s not found", analysis_id)
            return

        analysis.status = "analyzing"
        analysis.current_stage = "stub_processing"
        analysis.updated_at = datetime.now(UTC)
        db.commit()
        time.sleep(0.2)

        analysis.status = "completed"
        analysis.current_stage = None
        analysis.updated_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis is not None:
            analysis.status = "error"
            analysis.current_stage = None
            analysis.updated_at = datetime.now(UTC)
            db.commit()
        raise
    finally:
        db.close()
