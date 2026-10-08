"""add role, business_unit, is_active and last_login_at to users

Revision ID: 20260930_0022
Revises: 20260930_0021
Create Date: 2026-09-30
"""

import sqlalchemy as sa

from alembic import op
from infra.business_units import BUSINESS_UNITS, MAX_BUSINESS_UNIT_LENGTH
from users.roles import UserRole

revision = "20260930_0022"
down_revision = "20260930_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default=UserRole.MIEMBRO.value,
        ),
    )
    op.add_column(
        "users",
        sa.Column("business_unit", sa.String(length=MAX_BUSINESS_UNIT_LENGTH), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_business_unit", "users", ["business_unit"], unique=False)

    users = sa.table(
        "users",
        sa.column("role", sa.String),
        sa.column("business_unit", sa.String),
    )
    op.execute(
        users.update().values(role=UserRole.SUPERADMIN.value, business_unit=BUSINESS_UNITS[0])
    )


def downgrade() -> None:
    op.drop_index("ix_users_business_unit", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "business_unit")
    op.drop_column("users", "role")
