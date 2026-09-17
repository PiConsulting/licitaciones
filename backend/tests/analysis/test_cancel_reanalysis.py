"""Epic P5: cancelar un reanalisis no debe marcar todo el analisis como
"cancelled" ni esconder el boton de reanalizar -- eso es solo para cancelar un
analisis nuevo (la otra seccion). Cancelar un reanalisis en curso debe
descartar el intento y dejar el analisis como si nunca se hubiera disparado."""
from uuid import uuid4

import pytest

from analysis.models import Analysis, AnalysisVersion
from analysis.service.lifecycle import request_cancellation
from infra.database import SessionLocal
from users.models import User


def _get_owner_id() -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    db.close()
    assert user is not None
    return user.id


def _create_version(db, analysis_id: str, version_number: int, extracted_data: dict | None = None) -> AnalysisVersion:
    version = AnalysisVersion(
        analysis_id=analysis_id,
        version_number=version_number,
        extracted_data=extracted_data or {},
    )
    db.add(version)
    db.flush()
    return version


def test_cancel_fresh_analysis_marca_cancelled() -> None:
    """Sin metadata de reanalisis (analisis nuevo, la otra seccion): se
    preserva el comportamiento historico."""
    owner_id = _get_owner_id()
    db = SessionLocal()
    analysis = Analysis(created_by=owner_id, status="processing", correlation_id=str(uuid4()))
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    analysis_id = analysis.id
    db.close()

    result = SessionLocal()
    try:
        updated = request_cancellation(result, analysis_id, owner_id)
        assert updated.status == "cancelled"
        assert updated.error_message == "El analisis fue cancelado por el usuario"
    finally:
        result.close()


def test_cancel_reanalisis_con_clon_revierte_status_y_borra_el_clon() -> None:
    """Reanálisis tipo phase2/categories: clona la versión antes de re-extraer
    y repunta `current_version_id` al clon. Cancelar debe volver a la versión
    original y descartar el clon (que puede tener datos a medio actualizar)."""
    owner_id = _get_owner_id()
    db = SessionLocal()
    analysis = Analysis(created_by=owner_id, status="processing", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    source_version = _create_version(db, analysis.id, 1, {"objeto_alcance": "original"})
    clone_version = _create_version(db, analysis.id, 2, {"objeto_alcance": "a medio reanalizar"})
    db.flush()

    analysis.current_version_id = clone_version.id
    analysis.extraction_metadata = {
        "reanalysis_type": "categories",
        "reanalysis_categories": ["objeto_alcance"],
        "reanalysis_source_status": "analyzed",
        "reanalysis_source_version_id": source_version.id,
    }
    db.commit()
    analysis_id = analysis.id
    source_version_id = source_version.id
    clone_version_id = clone_version.id
    db.close()

    result = SessionLocal()
    try:
        updated = request_cancellation(result, analysis_id, owner_id)

        assert updated.status == "analyzed"
        assert updated.current_version_id == source_version_id
        assert "reanalysis_type" not in (updated.extraction_metadata or {})
        assert "reanalysis_source_status" not in (updated.extraction_metadata or {})
        assert "reanalysis_source_version_id" not in (updated.extraction_metadata or {})

        remaining = result.query(AnalysisVersion).filter(AnalysisVersion.id == clone_version_id).first()
        assert remaining is None, "el clon del reanalisis cancelado no deberia sobrevivir"

        source_still_there = (
            result.query(AnalysisVersion).filter(AnalysisVersion.id == source_version_id).first()
        )
        assert source_still_there is not None
        assert source_still_there.extracted_data == {"objeto_alcance": "original"}
    finally:
        result.close()


def test_cancel_reanalisis_sin_clon_mantiene_la_unica_version() -> None:
    """Reanálisis tipo phase1/all: no clona nada por adelantado -- la versión
    nueva se crea recién al terminar. Si se cancela antes de eso,
    `current_version_id` nunca cambió, así que no hay nada que borrar, solo
    hay que revertir el status."""
    owner_id = _get_owner_id()
    db = SessionLocal()
    analysis = Analysis(created_by=owner_id, status="processing", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    version = _create_version(db, analysis.id, 1, {"objeto_alcance": "original"})
    db.flush()

    analysis.current_version_id = version.id
    analysis.extraction_metadata = {
        "reanalysis_type": "phase1",
        "reanalysis_source_status": "en_revision",
        "reanalysis_source_version_id": version.id,
    }
    db.commit()
    analysis_id = analysis.id
    version_id = version.id
    db.close()

    result = SessionLocal()
    try:
        updated = request_cancellation(result, analysis_id, owner_id)

        assert updated.status == "en_revision"
        assert updated.current_version_id == version_id

        still_there = result.query(AnalysisVersion).filter(AnalysisVersion.id == version_id).first()
        assert still_there is not None
        assert still_there.extracted_data == {"objeto_alcance": "original"}
    finally:
        result.close()


def test_cancel_analisis_ya_terminal_no_hace_nada_aunque_haya_metadata_vieja() -> None:
    """Metadata de un reanalisis previo (ya completado) no debe reactivarse:
    si el analisis ya esta en un status terminal, cancelar es un no-op, igual
    que antes de este cambio."""
    owner_id = _get_owner_id()
    db = SessionLocal()
    analysis = Analysis(created_by=owner_id, status="analyzed", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()
    version = _create_version(db, analysis.id, 2, {"objeto_alcance": "ya reanalizado"})
    db.flush()
    analysis.current_version_id = version.id
    analysis.extraction_metadata = {
        "reanalysis_type": "categories",
        "reanalysis_source_status": "analyzed",
        "reanalysis_source_version_id": str(uuid4()),
    }
    db.commit()
    analysis_id = analysis.id
    version_id = version.id
    db.close()

    result = SessionLocal()
    try:
        updated = request_cancellation(result, analysis_id, owner_id)
        assert updated.status == "analyzed"
        assert updated.current_version_id == version_id
    finally:
        result.close()
