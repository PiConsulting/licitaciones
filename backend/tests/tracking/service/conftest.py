"""Fixtures para tests/tracking/service/ -- necesitan DB (tablas tracking +
analyses/analysis_versions/users, todas ya en `Base.metadata`)."""
from __future__ import annotations

import pytest

from analysis.models import Analysis, AnalysisVersion
from infra.config import get_settings
from infra.database import Base, SessionLocal, engine
from tracking.models import Tracking, TrackingCategory, TrackingComment, TrackingItem  # noqa: F401
from users.models import User
from users.service import get_password_hash

OWNER_USER_ID = "tracking-owner"
OTHER_USER_ID = "tracking-other"


@pytest.fixture(autouse=True)
def setup_db():
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        User(
            id=OWNER_USER_ID,
            email="tracking-owner@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Tracking Owner",
        )
    )
    db.add(
        User(
            id=OTHER_USER_ID,
            email="tracking-other@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Tracking Other",
        )
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    get_settings.cache_clear()


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def analyzed_analysis(db_session) -> tuple[str, str]:
    """Analysis en estado 'analyzed' con una version -- listo para
    start_tracking. Devuelve (analysis_id, version_id)."""
    analysis = Analysis(
        id="tracking-test-analysis",
        created_by=OWNER_USER_ID,
        status="analyzed",
    )
    db_session.add(analysis)
    db_session.commit()

    extracted_data = {
        "requisitos_admisibilidad": [
            {
                "tipo": "certificado_fiscal",
                "valor": "Certificado fiscal vigente",
                "source_references": [
                    {"document_id": "doc-1", "page_number": 3, "citation": "debe presentar certificado"}
                ],
            },
            {
                "tipo": "seguro_caucion",
                "valor": "Seguro de caución",
                "source_references": [
                    {"document_id": "doc-1", "page_number": 4, "citation": "seguro de caucion obligatorio"}
                ],
            },
        ],
        "anexos_obligatorios": [
            {
                "tipo": "anexo_1",
                "valor": "Formulario de oferta",
                "source_references": [
                    {"document_id": "doc-1", "page_number": 5, "citation": "anexo I formulario"}
                ],
            }
        ],
    }
    version = AnalysisVersion(
        id="tracking-test-version",
        analysis_id=analysis.id,
        version_number=1,
        extracted_data=extracted_data,
        created_by=OWNER_USER_ID,
    )
    db_session.add(version)
    analysis.current_version_id = version.id
    db_session.commit()

    return analysis.id, version.id
