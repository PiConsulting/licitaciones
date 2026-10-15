"""chunks: metadata de embedding y de chunker (F4.0 del plan RAG 2026-10-05)

Revision ID: 20261005_0023
Revises: 20260930_0022
Create Date: 2026-10-05

Motivo: hoy no se sabe qué modelo de embedding, con qué dimensiones y con qué versión
de chunker se generó cada vector. Sin eso no se puede validar un reindex ni detectar
vectores mezclados. Columnas nulables: los chunks existentes quedan en NULL hasta reindexar.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0023"
down_revision = "20260930_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding_model", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dims", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("chunker_version", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "chunker_version")
    op.drop_column("chunks", "embedding_dims")
    op.drop_column("chunks", "embedding_model")
