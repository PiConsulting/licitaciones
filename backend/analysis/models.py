from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class CurrentStage(str, Enum):
    QUEUED = "queued"
    EXTRACTING_TEXT = "extracting_text"
    INDEXING = "indexing"
    ANALYZING = "analyzing"
    CONSOLIDATING = "consolidating"
    COMPLETED = "completed"


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("idx_analyses_created_by", "created_by"),
        Index("idx_analyses_status", "status"),
        Index("idx_analyses_correlation_id", "correlation_id"),
        Index("idx_analyses_current_stage", "current_stage"),
        Index("idx_analyses_status_started_at", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_versions.id", use_alter=True, name="fk_analyses_current_version_id"),
        nullable=True,
    )
    extraction_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default=CurrentStage.QUEUED.value, nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_warning_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents = relationship("Document", back_populates="analysis", cascade="all, delete-orphan")
    versions = relationship(
        "AnalysisVersion",
        back_populates="analysis",
        cascade="all, delete-orphan",
        foreign_keys="AnalysisVersion.analysis_id",
    )
    current_version = relationship("AnalysisVersion", foreign_keys=[current_version_id], post_update=True)


class AnalysisVersion(Base):
    __tablename__ = "analysis_versions"
    __table_args__ = (
        Index("idx_analysis_versions_analysis_id", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    analysis = relationship("Analysis", back_populates="versions", foreign_keys=[analysis_id])
