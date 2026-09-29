"""add tracking.started_by_name and analyses categories_decision fields

Revision ID: 20260925_0015
Revises: 20260923_0014
Create Date: 2026-09-25
"""

import sqlalchemy as sa

from alembic import op

revision = "20260925_0015"
down_revision = "20260923_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracking", sa.Column("started_by_name", sa.Text(), nullable=True))

    op.add_column("analyses", sa.Column("categories_decision", sa.String(length=20), nullable=True))
    op.add_column(
        "analyses",
        sa.Column(
            "categories_decision_by",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column("analyses", sa.Column("categories_decision_by_name", sa.Text(), nullable=True))
    op.add_column(
        "analyses", sa.Column("categories_decision_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_analyses_categories_decision",
        "analyses",
        "categories_decision IN ('approved','rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_analyses_categories_decision", "analyses", type_="check")
    op.drop_column("analyses", "categories_decision_at")
    op.drop_column("analyses", "categories_decision_by_name")
    op.drop_column("analyses", "categories_decision_by")
    op.drop_column("analyses", "categories_decision")
    op.drop_column("tracking", "started_by_name")
