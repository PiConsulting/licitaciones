"""add indexes for analysis history list

Revision ID: 20260806_0006
Revises: 20260804_0005
Create Date: 2026-08-06
"""

import sqlalchemy as sa

from alembic import op

revision = "20260806_0006"
down_revision = "20260804_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_analyses_created_at", "analyses", ["created_at"], unique=False, if_not_exists=True)
    op.create_index("idx_analyses_status", "analyses", ["status"], unique=False, if_not_exists=True)
    op.create_index("idx_analyses_deleted_at", "analyses", ["deleted_at"], unique=False, if_not_exists=True)
    op.create_index(
        "idx_analyses_list",
        "analyses",
        ["deleted_at", sa.text("created_at DESC"), "status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_documents_lower_filename",
        "documents",
        [sa.text("lower(filename)")],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_documents_lower_filename", table_name="documents", if_exists=True)
    op.drop_index("idx_analyses_list", table_name="analyses", if_exists=True)
    op.drop_index("idx_analyses_deleted_at", table_name="analyses", if_exists=True)
    op.drop_index("idx_analyses_status", table_name="analyses", if_exists=True)
    op.drop_index("idx_analyses_created_at", table_name="analyses", if_exists=True)
