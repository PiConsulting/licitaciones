"""create analyses and documents tables

Revision ID: 20260803_0002
Revises: 20260803_0001
Create Date: 2026-08-03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260803_0002"
down_revision = "20260803_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("current_stage", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analyses_created_by", "analyses", ["created_by"], unique=False)
    op.create_index("idx_analyses_status", "analyses", ["status"], unique=False)
    op.create_index("idx_analyses_correlation_id", "analyses", ["correlation_id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("blob_name", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_documents_analysis_id", "documents", ["analysis_id"], unique=False)
    op.create_index("idx_documents_sha256_hash", "documents", ["sha256_hash"], unique=False)
    op.create_index("idx_documents_created_by", "documents", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_documents_created_by", table_name="documents")
    op.drop_index("idx_documents_sha256_hash", table_name="documents")
    op.drop_index("idx_documents_analysis_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("idx_analyses_correlation_id", table_name="analyses")
    op.drop_index("idx_analyses_status", table_name="analyses")
    op.drop_index("idx_analyses_created_by", table_name="analyses")
    op.drop_table("analyses")
