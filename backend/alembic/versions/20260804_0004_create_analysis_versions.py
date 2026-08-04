"""create analysis_versions and extraction metadata

Revision ID: 20260804_0004
Revises: 20260804_0003
Create Date: 2026-08-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260804_0004"
down_revision = "20260804_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("extracted_data", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "version_number", name="uq_analysis_versions_analysis_version"),
    )
    op.create_index("idx_analysis_versions_analysis_id", "analysis_versions", ["analysis_id"], unique=False)

    op.add_column("analyses", sa.Column("extraction_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "extraction_metadata")
    op.drop_index("idx_analysis_versions_analysis_id", table_name="analysis_versions")
    op.drop_table("analysis_versions")
