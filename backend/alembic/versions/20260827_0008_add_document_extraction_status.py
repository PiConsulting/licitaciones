"""add extraction_status/extraction_error to documents

Revision ID: 20260827_0008
Revises: 20260810_0007
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "20260827_0008"
down_revision = "20260810_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("extraction_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "documents",
        sa.Column("extraction_error", sa.String(length=1000), nullable=True),
    )
    op.alter_column("documents", "extraction_status", server_default=None)


def downgrade() -> None:
    op.drop_column("documents", "extraction_error")
    op.drop_column("documents", "extraction_status")
