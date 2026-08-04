"""add content_hash to documents

Revision ID: 20260804_0003
Revises: 20260803_0002
Create Date: 2026-08-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260804_0003"
down_revision = "20260803_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("idx_documents_content_hash", "documents", ["content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
