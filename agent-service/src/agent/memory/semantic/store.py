"""Semantic memory store — durable facts over PostgreSQL (ADR-0002, ADR-0003).

Mirrors Waku's ``SqliteFactStore`` surface (``add`` / ``search`` returning
ready-to-inject strings), adapted to our serverless Postgres: the store holds
the :class:`~agent.memory.db.Database`, not a live connection, and every method
opens a *short* session and hands it straight back. It delegates the SQL to
:class:`~agent.memory.repositories.FactRepository`, keeping the transactional,
session-injected data-access seam as the single source of truth for queries.

Retrieval is **vector-primary with a full-text fallback** (ADR-0003):

1. Embed the text — an external HTTP call, made *before* any session is opened,
   so no DB connection is ever held across it (CLAUDE.md §3, rag-design.md §5).
2. Open a short session and rank by cosine distance in Postgres.
3. If embedding fails, fall back to the retained ``content_tsv`` keyword search
   instead of returning nothing (ADR-0003 §7). The degradation is logged, never
   silent (CLAUDE.md §6) — the store keeps Waku's signatures, so reporting goes
   to structlog rather than through the facade's `notify` channel (which Waku
   reserves for the gate and consolidation).

With no embedder wired, the store is pure FTS — the pre-ADR-0003 behaviour.
"""

from __future__ import annotations

import structlog

from agent.memory.db import Database
from agent.memory.embeddings import Embedder, EmbeddingError
from agent.memory.repositories import FactRepository

_log = structlog.get_logger(__name__)


class PostgresFactStore:
    """Waku-style fact store: call it without managing a session yourself."""

    def __init__(self, db: Database, embedder: Embedder | None = None) -> None:
        self._db = db
        self._embedder = embedder

    async def add(
        self,
        subject: str,
        content: str,
        source: str = "user",
        user_id: str | None = None,
    ) -> None:
        """Store a fact, embedding it first so the write session stays short.

        A failed embedding does not lose the fact: it is written without a
        vector and remains findable by full text (and re-embeddable later).
        ``user_id`` scopes the fact to its owner (docs/SECURITY.md §3).
        """
        embedding: list[float] | None = None
        model: str | None = None
        if self._embedder is not None:
            try:
                vectors = await self._embedder.embed_documents(
                    [f"{subject}: {content}"]
                )
                embedding, model = vectors[0], self._embedder.model
            except EmbeddingError as exc:
                _log.warning("fact_embedding_failed", operation="add", error=str(exc))

        async with self._db.session() as session:
            await FactRepository(session).add(
                subject,
                content,
                source,
                user_id=user_id,
                embedding=embedding,
                embedding_model=model,
            )

    async def search(
        self, query: str, user_id: str | None, top_k: int = 4
    ) -> list[str]:
        """Most-relevant facts for this owner, formatted for injection as
        ``[subject] content``. Never returns another user's facts.

        Strings are built while the session is still open — the ORM rows are not
        used after the ``with`` block closes.
        """
        embedding: list[float] | None = None
        if self._embedder is not None:
            try:
                embedding = await self._embedder.embed_query(query)
            except EmbeddingError as exc:
                # Degrade to keyword search rather than returning nothing.
                _log.warning(
                    "fact_embedding_failed", operation="search", error=str(exc)
                )

        async with self._db.session() as session:
            repo = FactRepository(session)
            facts = (
                await repo.search_semantic(embedding, user_id, limit=top_k)
                if embedding is not None
                else await repo.search(query, user_id, limit=top_k)
            )
            return [f"[{fact.subject}] {fact.content}" for fact in facts]
