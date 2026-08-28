from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base

EMBEDDING_DIMENSIONS = 3072


class Chunk(Base):
    """Chunk indexado con embedding pgvector y texto para BM25 (`content_tsv`,
    columna generada por Postgres — no se mapea acá, es de solo lectura vía SQL).
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_analysis_id", "analysis_id"),
        Index("ix_chunks_document_id", "document_id"),
        CheckConstraint("chunk_type IN ('normal', 'parent', 'child')", name="ck_chunks_chunk_type"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[list | None] = mapped_column(JSON, nullable=True)
    heading_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primary_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    chunk_type: Mapped[str] = mapped_column(Text, default="normal", nullable=False)
    parent_chunk_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chunks.id"), nullable=True)
    child_chunk_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
