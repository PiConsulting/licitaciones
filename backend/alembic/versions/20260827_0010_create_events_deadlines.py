"""create events and deadlines tables (Historia 22.7, timeline)

Revision ID: 20260827_0010
Revises: 20260827_0009
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "20260827_0010"
down_revision = "20260827_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("date_source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "source_document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_fragment", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.JSON(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "date_source IN ('detected','user_input','calculated','pending')",
            name="ck_events_date_source",
        ),
        sa.CheckConstraint("status IN ('pending','confirmed')", name="ck_events_status"),
    )
    op.create_index(
        "ix_events_analysis_id",
        "events",
        ["analysis_id"],
        postgresql_where=sa.text("NOT deleted"),
    )

    op.create_table(
        "deadlines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("trigger_event_id", sa.String(length=36), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("target_event_id", sa.String(length=36), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("day_type", sa.String(length=20), nullable=False),
        sa.Column("direccion", sa.String(length=20), nullable=True),
        sa.Column("es_plazo_maximo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("calculation_status", sa.String(length=20), nullable=False),
        sa.Column("calculation_error", sa.Text(), nullable=True),
        sa.Column(
            "source_document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_fragment", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.JSON(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("duration >= 0", name="ck_deadlines_duration"),
        sa.CheckConstraint("unit IN ('días','meses','años','horas')", name="ck_deadlines_unit"),
        sa.CheckConstraint(
            "day_type IN ('corridos','hábiles','no_especificado')", name="ck_deadlines_day_type"
        ),
        sa.CheckConstraint(
            "direccion IN ('desde','hasta','antes_de','después_de') OR direccion IS NULL",
            name="ck_deadlines_direccion",
        ),
        sa.CheckConstraint(
            "calculation_status IN ('pending','calculated','error')",
            name="ck_deadlines_calc_status",
        ),
    )
    op.create_index(
        "ix_deadlines_analysis_id",
        "deadlines",
        ["analysis_id"],
        postgresql_where=sa.text("NOT deleted"),
    )


def downgrade() -> None:
    op.drop_table("deadlines")
    op.drop_table("events")
