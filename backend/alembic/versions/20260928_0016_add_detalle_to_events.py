"""add events.detalle (descripcion breve sintetizada del hito)

Revision ID: 20260928_0016
Revises: 20260925_0015
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0016"
down_revision = "20260925_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("detalle", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "detalle")
