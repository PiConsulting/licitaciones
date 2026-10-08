from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
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
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database import Base


class CurrentStage(str, Enum):
    QUEUED = "queued"
    EXTRACTING_TEXT = "extracting_text"
    INDEXING = "indexing"
    ANALYZING = "analyzing"
    CONSOLIDATING = "consolidating"
    COMPLETED = "completed"


class BusinessStatus(str, Enum):
    """
    Ciclo de vida comercial de una licitación (Epic FE5), independiente del
    estado operativo del análisis (`Analysis.status`) y del seguimiento por
    categorías (Epic 9, `tracking.*`).

    Flujo: EN_ANALISIS -> PENDIENTE_DECISION -> (NO_APROBADA | EN_REVISION)
    -> PRESENTADA -> (GANADA | PERDIDA). Una licitación NO_APROBADA puede
    reabrirse más adelante (vuelve a PENDIENTE_DECISION o EN_REVISION); la
    validación de transiciones se define en Story FE5.2, no acá.
    """
    EN_ANALISIS = "en_analisis"
    PENDIENTE_DECISION = "pendiente_decision"
    NO_APROBADA = "no_aprobada"
    EN_REVISION = "en_revision"
    PRESENTADA = "presentada"
    GANADA = "ganada"
    PERDIDA = "perdida"


class Analysis(Base):
    """
    Modelo de análisis de documentos. Cada análisis puede tener múltiples versiones (AnalysisVersion)
    que representan diferentes estados de los datos extraídos y procesados.

    Campos:
        id: Identificador único del análisis (UUID)
        created_by: ID del usuario que creó el análisis
        current_version_id: ID de la versión actual del análisis (puede ser None si no
        hay versiones)
        extraction_metadata: Metadatos relacionados con la extracción de datos
        analysis_name: Nombre del análisis (opcional)
        status: Estado del análisis (draft|queued|processing|en_revision|analyzed|error|cancelled)
        business_status: Estado de negocio de la licitación (Epic FE5, ver `BusinessStatus`),
        independiente de `status` y del seguimiento por categorías (Epic 9)
        current_stage: Etapa actual del análisis (queued|extracting_text|indexing|analyzing|consolidating|completed)
        progress_percentage: Porcentaje de progreso del análisis (0-100)
        timeout_warning_at: Timestamp de advertencia de timeout (opcional)
        timeout_at: Timestamp de timeout (opcional)
        started_at: Timestamp de inicio del análisis (opcional)
        cancellation_requested: Indica si se solicitó la cancelación del análisis
        error_message: Mensaje de error en caso de fallo (opcional)
        correlation_id: ID de correlación para rastreo (UUID)
        created_at: Timestamp de creación del registro
        updated_at: Timestamp de última actualización del registro
        deleted_at: Timestamp de eliminación (soft delete, opcional)

    """
    __tablename__ = "analyses"
    __table_args__ = (
        Index("idx_analyses_created_by", "created_by"),
        Index("idx_analyses_status", "status"),
        Index("idx_analyses_correlation_id", "correlation_id"),
        Index("idx_analyses_current_stage", "current_stage"),
        Index("idx_analyses_status_started_at", "status", "started_at"),
        Index("idx_analyses_business_status", "business_status"),
        CheckConstraint(
            "categories_decision IN ('approved','rejected')",
            name="ck_analyses_categories_decision",
        ),
        CheckConstraint(
            "business_status IN ("
            "'en_analisis','pendiente_decision','no_aprobada',"
            "'en_revision','presentada','ganada','perdida'"
            ")",
            name="ck_analyses_business_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    categories_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    categories_decision_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    categories_decision_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories_decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_versions.id", use_alter=True, name="fk_analyses_current_version_id"),
        nullable=True,
    )
    extraction_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    business_unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    business_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_stage: Mapped[str] = mapped_column(
        String(50), default=CurrentStage.QUEUED.value, nullable=False
    )
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_warning_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4())
    )
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
    current_version = relationship(
        "AnalysisVersion", foreign_keys=[current_version_id], post_update=True
    )
    business_status_history = relationship(
        "BusinessStatusHistory",
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="BusinessStatusHistory.changed_at",
    )
    presentation = relationship(
        "AnalysisPresentation",
        back_populates="analysis",
        cascade="all, delete-orphan",
        uselist=False,
    )
    result = relationship(
        "AnalysisResult",
        back_populates="analysis",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AnalysisVersion(Base):
    """
    Modelo de versión de análisis. Cada versión representa un estado específico de los datos extraídos y procesados.

    Campos:
        id: Identificador único de la versión (UUID)
        analysis_id: ID del análisis al que pertenece esta versión
        version_number: Número de versión
        extracted_data: Datos extraídos en esta versión
        conflicts: Conflictos detectados en esta versión (opcional)
        created_by: ID del usuario que creó la versión (opcional)
        created_at: Timestamp de creación del registro
    """
    __tablename__ = "analysis_versions"
    __table_args__ = (Index("idx_analysis_versions_analysis_id", "analysis_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    analysis = relationship("Analysis", back_populates="versions", foreign_keys=[analysis_id])


class BusinessStatusHistory(Base):
    """
    Historial auditable de cambios de `Analysis.business_status` (Epic FE5).
    Tabla insert-only, mismo patrón que `AnalysisVersion`: no aplica soft delete.

    Campos:
        id: Identificador único del registro de historial (UUID)
        analysis_id: ID del análisis al que pertenece el cambio
        previous_status: Estado de negocio anterior (`BusinessStatus`, opcional si es
        el primer registro)
        new_status: Estado de negocio nuevo (`BusinessStatus`)
        changed_by: ID del usuario que realizó el cambio (opcional, permite cambios
        originados por el sistema)
        changed_at: Timestamp del cambio
    """
    __tablename__ = "business_status_history"
    __table_args__ = (Index("idx_business_status_history_analysis_id", "analysis_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis = relationship(
        "Analysis", back_populates="business_status_history", foreign_keys=[analysis_id]
    )


class AnalysisPresentation(Base):
    __tablename__ = "analysis_presentations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    presented_at: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ARS")
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    offer_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_blob_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    analysis = relationship("Analysis", back_populates="presentation", foreign_keys=[analysis_id])


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        CheckConstraint("outcome IN ('ganada','perdida')", name="ck_analysis_results_outcome"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    resulted_at: Mapped[date] = mapped_column(Date, nullable=False)
    awarded_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    winner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    winner_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    analysis = relationship("Analysis", back_populates="result", foreign_keys=[analysis_id])
