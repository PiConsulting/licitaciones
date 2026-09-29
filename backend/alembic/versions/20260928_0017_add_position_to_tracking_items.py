"""add tracking_items.position (orden estable, faltaba ORDER BY explícito)

Revision ID: 20260928_0017
Revises: 20260928_0016
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0017"
down_revision = "20260928_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracking_items", sa.Column("position", sa.Integer(), nullable=False, server_default="0")
    )
    # Backfill: sin esta columna nunca hubo un orden garantizado, así que la
    # verdadera posición de creación no es recuperable -- se congela el orden
    # físico actual (`ctid`, el más cercano a lo que el usuario ya venía
    # viendo) para que a partir de acá el orden deje de moverse solo.
    op.execute(
        """
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY tracking_category_id ORDER BY ctid) - 1 AS rn
            FROM tracking_items
        )
        UPDATE tracking_items
        SET position = ordered.rn
        FROM ordered
        WHERE tracking_items.id = ordered.id
        """
    )
    op.alter_column("tracking_items", "position", server_default=None)


def downgrade() -> None:
    op.drop_column("tracking_items", "position")
