"""add presentation, result and history note for business status

Revision ID: 20260929_0019
Revises: 20260928_0018
Create Date: 2026-09-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20260929_0019"
down_revision = "20260928_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_status_history", sa.Column("note", sa.Text(), nullable=True))

    op.create_table(
        "analysis_presentations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("presented_at", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="ARS"),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("offer_number", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("resulted_at", sa.Date(), nullable=False),
        sa.Column("awarded_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("loss_reason", sa.String(length=40), nullable=True),
        sa.Column("winner_name", sa.String(length=200), nullable=True),
        sa.Column("winner_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("outcome IN ('ganada','perdida')", name="ck_analysis_results_outcome"),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("analysis_presentations")
    op.drop_column("business_status_history", "note")
