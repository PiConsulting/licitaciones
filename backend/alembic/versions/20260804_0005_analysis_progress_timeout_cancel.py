"""add analysis progress, timeout and cancellation fields

Revision ID: 20260804_0005
Revises: 20260804_0004
Create Date: 2026-08-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260804_0005"
down_revision = "20260804_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill legacy rows before setting NOT NULL.
    op.execute("UPDATE analyses SET current_stage = 'queued' WHERE current_stage IS NULL")
    op.alter_column("analyses", "current_stage", existing_type=sa.String(length=100), nullable=False, server_default="queued")
    op.add_column("analyses", sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analyses", sa.Column("timeout_warning_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyses", sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyses", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyses", sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("analyses", sa.Column("error_message", sa.String(length=500), nullable=True))

    op.create_index("idx_analyses_current_stage", "analyses", ["current_stage"], unique=False)
    op.create_index("idx_analyses_status_started_at", "analyses", ["status", "started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_analyses_status_started_at", table_name="analyses")
    op.drop_index("idx_analyses_current_stage", table_name="analyses")

    op.drop_column("analyses", "error_message")
    op.drop_column("analyses", "cancellation_requested")
    op.drop_column("analyses", "started_at")
    op.drop_column("analyses", "timeout_at")
    op.drop_column("analyses", "timeout_warning_at")
    op.drop_column("analyses", "progress_percentage")
    op.alter_column("analyses", "current_stage", existing_type=sa.String(length=100), nullable=True, server_default=None)
