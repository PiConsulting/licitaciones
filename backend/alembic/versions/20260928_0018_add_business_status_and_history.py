"""add business_status to analyses and business_status_history table (Story FE5.1)

Revision ID: 20260928_0018
Revises: 20260928_0017
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision = "20260928_0018"
down_revision = "20260928_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("business_status", sa.String(length=50), nullable=True))
    op.create_index("idx_analyses_business_status", "analyses", ["business_status"], unique=False)
    op.create_check_constraint(
        "ck_analyses_business_status",
        "analyses",
        "business_status IN ("
        "'en_analisis','pendiente_decision','no_aprobada',"
        "'en_revision','presentada','ganada','perdida'"
        ")",
    )

    op.create_table(
        "business_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "idx_business_status_history_analysis_id", "business_status_history", ["analysis_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_business_status_history_analysis_id", table_name="business_status_history")
    op.drop_table("business_status_history")

    op.drop_constraint("ck_analyses_business_status", "analyses", type_="check")
    op.drop_index("idx_analyses_business_status", table_name="analyses")
    op.drop_column("analyses", "business_status")
