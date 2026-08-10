"""add optional analysis_name to analyses

Revision ID: 20260810_0007
Revises: 20260806_0006
Create Date: 2026-08-10
"""

import sqlalchemy as sa

from alembic import op

revision = "20260810_0007"
down_revision = "20260806_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("analysis_name", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "analysis_name")
