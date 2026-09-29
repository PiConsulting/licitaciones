"""add business_unit to analyses

Revision ID: 20260923_0014
Revises: 20260909_0013
Create Date: 2026-09-23
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_0014"
down_revision = "20260909_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("business_unit", sa.String(length=80), nullable=True))
    op.create_index("idx_analyses_business_unit", "analyses", ["business_unit"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_analyses_business_unit", table_name="analyses")
    op.drop_column("analyses", "business_unit")
