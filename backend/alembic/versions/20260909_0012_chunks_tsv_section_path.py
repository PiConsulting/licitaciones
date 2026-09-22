"""chunks.content_tsv: incluir el heading path completo (section_path) con peso, no solo el title (hoja)

Revision ID: 20260909_0012
Revises: 20260827_0011
Create Date: 2026-09-09

Motivo (plan rag-plan-latencia-2026-09-09, reindex A+B): la columna generada
`content_tsv` usaba `coalesce(title,'') || ' ' || content`, donde `title` es
solo `heading_path[-1]` (la hoja). Los headings ancestros -- que son la señal
lexica de "esto es un anexo / una garantia / un requisito" -- no entraban al
indice BM25. Ahora el vector de texto pesa el `section_path` completo (rank A)
sobre el contenido (rank B), asi una query con "anexo"/"formulario"/
"declaracion jurada" matchea chunks bajo esos encabezados aunque el cuerpo no
repita la palabra. `content_tsv` es GENERATED ALWAYS -> se recalcula solo para
todas las filas al recrear la columna, sin reindex de datos.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

revision = "20260909_0012"
down_revision = "20260827_0011"
branch_labels = None
depends_on = None

_NEW_EXPR = (
    "setweight(to_tsvector('spanish', coalesce(section_path, '')), 'A') || "
    "setweight(to_tsvector('spanish', content), 'B')"
)
_OLD_EXPR = "to_tsvector('spanish', coalesce(title, '') || ' ' || content)"


def _swap_content_tsv(expr: str) -> None:
    # Generated columns can't ALTER their expression -> drop+re-add; the GIN index depends on it so it's recreated after.
    op.drop_index("ix_chunks_content_tsv", table_name="chunks")
    op.drop_column("chunks", "content_tsv")
    op.add_column(
        "chunks",
        sa.Column(
            "content_tsv",
            TSVECTOR(),
            sa.Computed(expr, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_chunks_content_tsv", "chunks", ["content_tsv"], postgresql_using="gin"
    )


def upgrade() -> None:
    _swap_content_tsv(_NEW_EXPR)


def downgrade() -> None:
    _swap_content_tsv(_OLD_EXPR)
