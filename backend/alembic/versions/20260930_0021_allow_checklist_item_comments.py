"""allow checklist item scope in tracking comments

Revision ID: 20260930_0021
Revises: 20260930_0020
Create Date: 2026-09-30
"""

from alembic import op

revision = "20260930_0021"
down_revision = "20260930_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_tracking_comments_scope", "tracking_comments", type_="check")
    op.create_check_constraint(
        "ck_tracking_comments_scope",
        "tracking_comments",
        "scope IN ('category', 'checklist_item')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM tracking_comments WHERE scope <> 'category'")
    op.drop_constraint("ck_tracking_comments_scope", "tracking_comments", type_="check")
    op.create_check_constraint(
        "ck_tracking_comments_scope",
        "tracking_comments",
        "scope = 'category'",
    )
