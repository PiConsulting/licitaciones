"""Modelos SQLAlchemy de Tracking -- normalización completa (Historia 22.8,
decisión #1 del plan: priorizar la base más limpia posible sobre el menor
esfuerzo, en vez de guardar el árbol categories/items como JSONB).

`events` en `Tracking`/`TrackingCategory` es un log de auditoría interno
(nunca expuesto por `tracking/schemas.py`) -- se preserva como JSONB en vez
de tablas dedicadas, mismo criterio que `summary` en el plan ("agregado de
bajo valor de consulta, JSONB aceptable").
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database import Base


class Tracking(Base):
    __tablename__ = "tracking"
    __table_args__ = (
        UniqueConstraint("analysis_id", "version_id", name="uq_tracking_analysis_version"),
        CheckConstraint("status IN ('active','completed')", name="ck_tracking_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_versions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    started_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    completed_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    events: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    categories = relationship(
        "TrackingCategory", back_populates="tracking", cascade="all, delete-orphan"
    )


class TrackingCategory(Base):
    __tablename__ = "tracking_categories"
    __table_args__ = (
        UniqueConstraint("tracking_id", "category_key", name="uq_tracking_categories_key"),
        CheckConstraint(
            "status IN ('not_reviewed','in_review','closed')", name="ck_tracking_categories_status"
        ),
        Index("ix_tracking_categories_tracking_id", "tracking_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tracking_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tracking.id", ondelete="CASCADE"), nullable=False
    )
    category_key: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_reviewed")
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    tracking = relationship("Tracking", back_populates="categories")
    items = relationship("TrackingItem", back_populates="category", cascade="all, delete-orphan")


class TrackingItem(Base):
    __tablename__ = "tracking_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_evaluated','compliant','non_compliant','not_applicable')",
            name="ck_tracking_items_status",
        ),
        Index("ix_tracking_items_category_id", "tracking_category_id"),
    )

    # Hash determinista generado en categories.py (_build_tracking_item_id); igual que Cosmos.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tracking_category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tracking_categories.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_evaluated")
    source_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_field_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_citation_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category = relationship("TrackingCategory", back_populates="items")


class TrackingComment(Base):
    __tablename__ = "tracking_comments"
    __table_args__ = (
        CheckConstraint("scope = 'category'", name="ck_tracking_comments_scope"),
        Index("ix_tracking_comments_analysis_category", "analysis_id", "category_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    category_key: Mapped[str] = mapped_column(String(60), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="category")
    tracking_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    edited_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    edited_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
