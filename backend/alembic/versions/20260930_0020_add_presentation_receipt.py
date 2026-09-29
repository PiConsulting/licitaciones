"""add receipt columns to analysis presentations

Revision ID: 20260930_0020
Revises: 20260929_0019
Create Date: 2026-09-30
"""

import sqlalchemy as sa

from alembic import op

revision = "20260930_0020"
down_revision = "20260929_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_presentations",
        sa.Column("receipt_blob_name", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "analysis_presentations",
        sa.Column("receipt_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "analysis_presentations",
        sa.Column("receipt_content_type", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_presentations", "receipt_content_type")
    op.drop_column("analysis_presentations", "receipt_filename")
    op.drop_column("analysis_presentations", "receipt_blob_name")
