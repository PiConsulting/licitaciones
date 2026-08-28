"""create chunks table with pgvector embedding + tsvector for BM25

Revision ID: 20260827_0009
Revises: 20260827_0008
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

revision = "20260827_0009"
down_revision = "20260827_0008"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSIONS = 3072


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=True),
        sa.Column("heading_level", sa.Integer(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("block_type", sa.Text(), nullable=True),
        sa.Column("table_ref", sa.JSON(), nullable=True),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("primary_category", sa.Text(), nullable=True),
        sa.Column("secondary_categories", sa.JSON(), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_tsv",
            TSVECTOR(),
            sa.Computed("to_tsvector('spanish', coalesce(title, '') || ' ' || content)", persisted=True),
            nullable=True,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column(
            "chunk_type",
            sa.Text(),
            nullable=False,
            server_default="normal",
        ),
        sa.Column(
            "parent_chunk_id",
            sa.Text(),
            sa.ForeignKey("chunks.id"),
            nullable=True,
        ),
        sa.Column("child_chunk_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_type IN ('normal', 'parent', 'child')", name="ck_chunks_chunk_type"
        ),
    )

    op.create_index("ix_chunks_analysis_id", "chunks", ["analysis_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index(
        "ix_chunks_content_tsv", "chunks", ["content_tsv"], postgresql_using="gin"
    )
    # pgvector limita los índices HNSW/IVFFlat a 2000 dimensiones para el tipo `vector`
    # (el límite de 4000 es de `halfvec`, media precisión). text-embedding-3-large produce
    # 3072 dims, por encima del límite indexable de `vector` -- se indexa vía una expresión
    # halfvec (precisión reducida solo para el índice ANN; la columna `embedding` guarda
    # el vector completo sin pérdida). La query de la Historia 22.4 debe castear el
    # query_vector a ::halfvec(3072) también para que el índice se use.
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("chunks")
