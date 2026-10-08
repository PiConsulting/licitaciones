"""Conftest para tests/timeline/service/ -- necesitan DB (a diferencia de
test_calculator.py/test_event_model.py/etc, que son funciones puras). El
conftest.py padre de tests/timeline/ deshabilita el `setup_db` global para
esos tests puros; acá lo reactivamos (mismo patrón que `tests/conftest.py`
raíz, ver nota dejada ahí para este caso exacto).
"""
from __future__ import annotations

import pytest

from analysis.models import Analysis
from infra.config import get_settings
from infra.database import Base, SessionLocal, engine
from timeline.models_orm import (  # noqa: F401 -- registra tablas en Base.metadata
    DeadlineORM,
    EventORM,
)
from users.models import User
from users.service import get_password_hash

TEST_USER_ID = "timeline-test-user"
OTHER_USER_ID = "timeline-other-user"


@pytest.fixture(autouse=True)
def setup_db():
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        User(
            id=TEST_USER_ID,
            email="timeline-owner@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Timeline Owner",
        )
    )
    db.add(
        User(
            id=OTHER_USER_ID,
            email="timeline-other@cedia.com",
            password_hash=get_password_hash("Test1234!"),
            name="Timeline Other",
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
def analysis_id(db_session) -> str:
    analysis = Analysis(id="timeline-test-analysis", created_by=TEST_USER_ID)
    db_session.add(analysis)
    db_session.commit()
    return analysis.id
