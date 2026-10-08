"""Fixtures compartidas para tests que necesitan Postgres local real
(pgvector, `chunks`) -- Historias 22.3/22.4. `pg_session_factory` vive en el
conftest.py raíz (reusable por cualquier test que necesite Postgres real,
no solo indexing); acá solo el seed específico de indexing (analysis +
document, para las FKs de `chunks`).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text


@pytest.fixture
def seeded_analysis(pg_session_factory):
    """Crea un user/analysis/document reales (FKs de `chunks`) y los borra al
    final -- borrar `analyses` cascadea a `documents` y `chunks`."""
    import analysis.models as _analysis_models  # noqa: F401 -- registra FK target `analyses`
    import documents.models as _documents_models  # noqa: F401 -- registra FK target `documents`
    import users.models as _users_models  # noqa: F401 -- registra FK target `users`
    from analysis.models import Analysis
    from documents.models import Document
    from users.models import User

    db = pg_session_factory()
    user_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())

    db.add(
        User(
            id=user_id,
            email=f"{user_id}@smoke-test.local",
            password_hash="x",
            name="Smoke Test 22.x",
        )
    )
    db.commit()
    db.add(Analysis(id=analysis_id, created_by=user_id))
    db.commit()
    db.add(
        Document(
            id=document_id,
            analysis_id=analysis_id,
            filename="smoke.pdf",
            blob_name="smoke/smoke.pdf",
            file_size_bytes=1,
            page_count=1,
            sha256_hash="0" * 64,
            created_by=user_id,
        )
    )
    db.commit()
    db.close()

    yield analysis_id, document_id

    db = pg_session_factory()
    db.execute(text("DELETE FROM analyses WHERE id = :id"), {"id": analysis_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()
    db.close()
