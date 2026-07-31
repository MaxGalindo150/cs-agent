"""facts pgvector embedding column and hnsw index

Revision ID: 81eb545e5152
Revises: 899d3cd20b50
Create Date: 2026-07-22 14:34:38.488090

Adds semantic-memory vector retrieval to `agent.facts` (ADR-0003): a nullable
`halfvec` embedding + the model that produced it, and an HNSW cosine index
mirroring docs/rag-design.md. The existing `content_tsv` + GIN index are left in
place — they back the FTS fallback (ADR-0003 §7) and a future hybrid step.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC


# revision identifiers, used by Alembic.
revision: str = '81eb545e5152'
down_revision: Union[str, Sequence[str], None] = '899d3cd20b50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# fp16 vector dimension for facts.embedding. Frozen in this migration on
# purpose: a migration is a point-in-time snapshot and must not track a moving
# app constant. Matches agent.memory.models._FACT_EMBEDDING_DIMS at write time.
_EMBEDDING_DIMS = 1024


def upgrade() -> None:
    """Upgrade schema."""
    # pgvector ships with the platform Postgres image (ADR-0002 §4); enabling
    # the extension is idempotent. Created in `public` so the `halfvec` type and
    # `halfvec_cosine_ops` opclass resolve via search_path for every service in
    # the shared database, not only this schema.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")

    op.add_column(
        "facts",
        sa.Column("embedding", HALFVEC(_EMBEDDING_DIMS), nullable=True),
        schema="agent",
    )
    op.add_column(
        "facts",
        sa.Column("embedding_model", sa.Text(), nullable=True),
        schema="agent",
    )
    op.create_index(
        "ix_facts_embedding_hnsw",
        "facts",
        ["embedding"],
        unique=False,
        schema="agent",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_facts_embedding_hnsw",
        table_name="facts",
        schema="agent",
        postgresql_using="hnsw",
    )
    op.drop_column("facts", "embedding_model", schema="agent")
    op.drop_column("facts", "embedding", schema="agent")
    # The `vector` extension is intentionally left installed: it is shared across
    # services (e.g. the KB RAG system, docs/rag-design.md), so dropping it here
    # could break them.
