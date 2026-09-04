"""Deteccion de documentos ya analizados antes (mismo content_hash) para avisar al usuario."""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from analysis.models import Analysis
from documents.models import Document
from users.models import User


def check_duplicates(
    db: Session,
    content_hash: str,
    *,
    exclude_analysis_id: str | None = None,
    user_id: str | None = None,
) -> dict | None:
    stmt = (
        select(
            Document.id.label("document_id"),
            Document.filename,
            Document.content_hash,
            Analysis.id.label("analysis_id"),
            Analysis.created_at,
            Analysis.status,
            User.email.label("created_by_email"),
            User.name.label("created_by_name"),
        )
        .join(Analysis, Document.analysis_id == Analysis.id)
        .join(User, Analysis.created_by == User.id)
        .where(
            and_(
                Document.content_hash == content_hash,
                Analysis.deleted_at.is_(None),
                Document.deleted_at.is_(None),
                # `en_revision` cuenta como análisis ya procesado para alertar
                # duplicados aunque todavía no haya corrido fase 2.
                Analysis.status.in_(["completed", "analyzing", "analyzed", "en_revision"]),
            )
        )
    )

    if exclude_analysis_id:
        stmt = stmt.where(Analysis.id != exclude_analysis_id)

    if user_id:
        stmt = stmt.where(Analysis.created_by == user_id)

    result = db.execute(stmt.order_by(Analysis.created_at.desc()).limit(1)).first()
    if result is None:
        return None

    return {
        "document_id": str(result.document_id),
        "filename": result.filename,
        "analysis_id": str(result.analysis_id),
        "created_at": result.created_at.isoformat(),
        "status": result.status,
        "created_by_email": result.created_by_email,
        "created_by_name": result.created_by_name,
    }


def find_duplicates_for_analysis(db: Session, analysis_id: str, user_id: str) -> list[dict]:
    documents = (
        db.query(Document)
        .filter(
            Document.analysis_id == analysis_id,
            Document.deleted_at.is_(None),
            Document.content_hash.is_not(None),
        )
        .all()
    )

    duplicates: list[dict] = []
    for document in documents:
        duplicate = check_duplicates(
            db,
            document.content_hash or "",
            exclude_analysis_id=analysis_id,
            user_id=user_id,
        )
        if duplicate is None:
            continue

        duplicates.append(
            {
                "document_id": document.id,
                "filename": document.filename,
                "existing_analysis_id": duplicate["analysis_id"],
                "created_at": duplicate["created_at"],
                "created_by": duplicate["created_by_name"] or duplicate["created_by_email"],
                "status": duplicate["status"],
            }
        )

    return duplicates
