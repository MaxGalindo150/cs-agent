"""Integration test for the facts vector column + HNSW index (ADR-0003).

Proves migration 0003 applied end-to-end against real Postgres: the ``embedding``
halfvec column accepts a vector written as a plain Python list (no numpy on the
write path), and a cosine-distance ordering — the exact operation the fact
store's vector search will use in 3c — returns the nearest fact first. The
embedding is never read back into Python; retrieval ranks it in SQL.
"""

from __future__ import annotations

from sqlalchemy import select

from agent.memory.db import Database
from agent.memory.models import Fact


def _unit(*head: float) -> list[float]:
    """A 1024-dim vector: the given leading components, then zero-padded."""
    return [*head] + [0.0] * (1024 - len(head))


async def test_migration_0003_embedding_column_and_cosine_search(
    database: Database,
) -> None:
    async with database.session() as session:
        session.add_all(
            [
                Fact(
                    subject="vpn",
                    content="near",
                    embedding=_unit(1.0, 0.0),
                    embedding_model="voyage-3.5",
                ),
                Fact(
                    subject="billing",
                    content="far",
                    embedding=_unit(0.0, 1.0),
                    embedding_model="voyage-3.5",
                ),
            ]
        )

    probe = _unit(1.0, 0.0)
    async with database.session() as session:
        result = await session.execute(
            select(Fact.content)
            .order_by(Fact.embedding.cosine_distance(probe))
            .limit(1)
        )
        assert result.scalar_one() == "near"
