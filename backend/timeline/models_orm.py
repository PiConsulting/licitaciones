"""Modelos SQLAlchemy de Timeline (persistencia). Los modelos Pydantic de
`timeline/models.py` siguen siendo la capa de validación de dominio/API --
estos son solo la representación de fila SQL, convertida a/desde Pydantic en
`timeline/repository.py`.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base


class EventORM(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "date_source IN ('detected','user_input','calculated','pending')",
            name="ck_events_date_source",
        ),
        CheckConstraint("status IN ('pending','confirmed')", name="ck_events_status"),
        Index("ix_events_analysis_id", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_source: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # No hay Alembic en este repo -- columna agregada por migración manual (ALTER TABLE).
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class DeadlineORM(Base):
    __tablename__ = "deadlines"
    __table_args__ = (
        CheckConstraint("duration >= 0", name="ck_deadlines_duration"),
        CheckConstraint("unit IN ('días','meses','años','horas')", name="ck_deadlines_unit"),
        CheckConstraint(
            "day_type IN ('corridos','hábiles','no_especificado')", name="ck_deadlines_day_type"
        ),
        CheckConstraint(
            "direccion IN ('desde','hasta','antes_de','después_de') OR direccion IS NULL",
            name="ck_deadlines_direccion",
        ),
        CheckConstraint(
            "calculation_status IN ('pending','calculated','error')",
            name="ck_deadlines_calc_status",
        ),
        Index("ix_deadlines_analysis_id", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id"), nullable=True
    )
    target_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id"), nullable=True
    )
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="días")
    day_type: Mapped[str] = mapped_column(String(20), nullable=False, default="no_especificado")
    direccion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    es_plazo_maximo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    calculation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    calculation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
