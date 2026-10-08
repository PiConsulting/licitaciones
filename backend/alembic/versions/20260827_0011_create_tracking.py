"""create tracking tables, normalizado (Historia 22.8)

Revision ID: 20260827_0011
Revises: 20260827_0010
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "20260827_0011"
down_revision = "20260827_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracking",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id", sa.String(length=36), sa.ForeignKey("analysis_versions.id"), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_by_name", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.UniqueConstraint("analysis_id", "version_id", name="uq_tracking_analysis_version"),
        sa.CheckConstraint("status IN ('active','completed')", name="ck_tracking_status"),
    )

    op.create_table(
        "tracking_categories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tracking_id",
            sa.String(length=36),
            sa.ForeignKey("tracking.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_key", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.UniqueConstraint("tracking_id", "category_key", name="uq_tracking_categories_key"),
        sa.CheckConstraint(
            "status IN ('not_reviewed','in_review','closed')", name="ck_tracking_categories_status"
        ),
    )
    op.create_index(
        "ix_tracking_categories_tracking_id", "tracking_categories", ["tracking_id"]
    )

    op.create_table(
        "tracking_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tracking_category_id",
            sa.String(length=36),
            sa.ForeignKey("tracking_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_field_name", sa.Text(), nullable=True),
        sa.Column(
            "source_document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_citation_hash", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('not_evaluated','compliant','non_compliant','not_applicable')",
            name="ck_tracking_items_status",
        ),
    )
    op.create_index("ix_tracking_items_category_id", "tracking_items", ["tracking_category_id"])

    op.create_table(
        "tracking_comments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(length=36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("category_key", sa.String(length=60), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="category"),
        sa.Column("tracking_item_id", sa.String(length=36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("edited_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("edited_by_name", sa.Text(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("scope = 'category'", name="ck_tracking_comments_scope"),
    )
    op.create_index(
        "ix_tracking_comments_analysis_category", "tracking_comments", ["analysis_id", "category_key"]
    )


def downgrade() -> None:
    op.drop_table("tracking_comments")
    op.drop_table("tracking_items")
    op.drop_table("tracking_categories")
    op.drop_table("tracking")
