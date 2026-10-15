"""create sso_login_codes table (Historia 25.2: código de intercambio SSO de un solo uso)

Revision ID: 20261013_0024
Revises: 20261005_0023
Create Date: 2026-10-13

Motivo: el callback SSO no puede devolver el JWT final en la URL del redirect hacia el
frontend (expone la credencial en historial/logs/Referer). Este código de un solo uso y
vida corta (60s) es lo único que viaja por esa URL; el frontend lo canjea de inmediato
por el JWT real vía POST /auth/sso/exchange.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261013_0024"
down_revision = "20261005_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sso_login_codes",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("code"),
    )


def downgrade() -> None:
    op.drop_table("sso_login_codes")
