"""chunks.category_scores: vector multi-label {categoria: score 0-1} por chunk

Revision ID: 20260909_0013
Revises: 20260909_0012
Create Date: 2026-09-09

Plan rag-plan-latencia-2026-09-09, reindex C: hoy la clasificacion de chunks
es mono-label (`primary_category` + `secondary_categories` como lista de
membership). Un parrafo de pliego suele pertenecer a varias categorias con
distinta fuerza. Esta columna guarda el vector completo {categoria: score}
(score 0-1 = max de heading / keyword-density / similitud semantica). El
retrieval (`_score_chunks_for_category`) lo usa para un boost GRADUADO en vez
del +/-50%/15% binario sobre `primary`/`secondary`. Aditiva y no rompe nada:
`secondary_categories` (lista) sigue igual para los lectores que hacen
membership.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260909_0013"
down_revision = "20260909_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("category_scores", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "category_scores")
