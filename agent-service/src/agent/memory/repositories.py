"""Repositories over the agent's durable memory (ADR-0002).

Each repository is a thin, typed wrapper around SQL for one concern. They take
an ``AsyncSession`` rather than the ``Database`` itself, so the *caller* owns the
transaction scope::

    async with db.session() as s:              # short unit of work
        await SessionRepository(s).append_message(...)

That is deliberate: it keeps the "never hold a connection across an LLM call"
rule (CLAUDE.md §3) visible at the call site instead of hidden in here. A
repository never opens, commits, or closes a connection of its own.

Full-text search uses the generated ``tsvector`` columns with the ``spanish``
dictionary, matching how the columns are built (agent/memory/models.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent.memory.models import ChatMessage, ChatSession, Episode, Fact

# The dictionary must match the one in the generated tsvector columns, or the
# query's lexemes won't line up with the indexed ones.
_FTS_DICTIONARY = "spanish"


class SessionRepository:
    """Conversations: sessions and their raw message log."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create_session(
        self, title: str | None = None, user_id: str | None = None
    ) -> ChatSession:
        chat_session = ChatSession(title=title, user_id=user_id)
        self._db.add(chat_session)
        await self._db.flush()
        return chat_session

    async def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        return await self._db.get(ChatSession, session_id)

    async def list_sessions(self, limit: int = 50) -> list[ChatSession]:
        """Most recently active first — the order a chat sidebar wants."""
        result = await self._db.execute(
            select(ChatSession)
            .order_by(ChatSession.last_activity_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        """Delete a conversation. Returns False if it was already gone.

        Its ``chat_messages`` go with it: the FK is ``ON DELETE CASCADE``, so
        the database removes them in the same statement. A Core DELETE (rather
        than loading the row and letting the ORM cascade) keeps this to one
        round trip and never pulls the message log into memory just to discard
        it — the model declares ``passive_deletes=True`` for exactly this.
        """
        result = await self._db.execute(
            delete(ChatSession).where(ChatSession.id == session_id)
        )
        # DML always yields a CursorResult; only that subtype exposes rowcount.
        return cast(CursorResult[Any], result).rowcount > 0

    async def append_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> ChatMessage:
        """Append one turn and bump the session's activity clock.

        ``role`` is guarded by a CHECK constraint in the schema — an invalid
        value raises rather than silently landing in the log. ``source`` is the
        input channel (whatsapp/webchat/api); NULL when the caller doesn't know.
        """
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            source=source,
            meta=meta,
        )
        self._db.add(message)
        await self._db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(last_activity_at=func.now())
        )
        await self._db.flush()
        return message

    async def list_messages(
        self, session_id: uuid.UUID, limit: int = 200
    ) -> list[ChatMessage]:
        """Oldest first — the order the model expects history in.

        Ordered by `seq` (insertion order), never by `created_at`: the latter is
        the transaction timestamp and is identical for messages written in one
        transaction.
        """
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_unconsolidated(self, limit: int = 500) -> list[ChatMessage]:
        """What the consolidation worker still has to distil."""
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.consolidated.is_(False))
            .order_by(ChatMessage.seq)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_consolidated(self, message_ids: list[uuid.UUID]) -> int:
        """Mark messages as distilled. Returns how many rows changed."""
        if not message_ids:
            return 0
        result = await self._db.execute(
            update(ChatMessage)
            .where(ChatMessage.id.in_(message_ids))
            .values(consolidated=True)
        )
        # DML always yields a CursorResult; only that subtype exposes rowcount.
        # Spelled without quotes so the imported names are real references —
        # a quoted cast target reads as an unused import to static analysis.
        return cast(CursorResult[Any], result).rowcount


class FactRepository:
    """Semantic memory: durable facts, retrieved by subject or full text."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def add(
        self,
        subject: str,
        content: str,
        source: str = "user",
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Fact:
        """Store a fact, optionally with its embedding (ADR-0003).

        ``embedding`` is left NULL when embedding is unavailable — the fact is
        still written and stays findable by full text.
        """
        fact = Fact(
            subject=subject,
            content=content,
            source=source,
            embedding=embedding,
            embedding_model=embedding_model if embedding is not None else None,
        )
        self._db.add(fact)
        await self._db.flush()
        return fact

    async def list_by_subject(self, subject: str, limit: int = 50) -> list[Fact]:
        result = await self._db.execute(
            select(Fact)
            .where(Fact.subject == subject)
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search(self, query: str, limit: int = 20) -> list[Fact]:
        """Full-text search, most relevant first.

        ``plainto_tsquery`` takes a plain phrase (no operator syntax), so
        untrusted text can be passed straight through — it cannot inject query
        operators.
        """
        tsquery = func.plainto_tsquery(_FTS_DICTIONARY, query)
        rank = func.ts_rank(Fact.content_tsv, tsquery)
        result = await self._db.execute(
            select(Fact)
            .where(Fact.content_tsv.op("@@")(tsquery))
            .order_by(rank.desc(), Fact.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_semantic(
        self, embedding: list[float], limit: int = 20
    ) -> list[Fact]:
        """Nearest facts by meaning — cosine distance over the HNSW index.

        Ranking happens entirely in Postgres (``<=>``); the stored vectors are
        never loaded into Python. Rows without an embedding are excluded rather
        than sorted last: a NULL distance would otherwise pollute the ordering.
        """
        result = await self._db.execute(
            select(Fact)
            .where(Fact.embedding.is_not(None))
            .order_by(Fact.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())


class EpisodeRepository:
    """Episodic memory: dated summaries, retrieved by recency or full text."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def add(self, happened_at: datetime, summary: str) -> Episode:
        episode = Episode(happened_at=happened_at, summary=summary)
        self._db.add(episode)
        await self._db.flush()
        return episode

    async def list_recent(self, limit: int = 20) -> list[Episode]:
        result = await self._db.execute(
            select(Episode).order_by(Episode.happened_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def search(self, query: str, limit: int = 20) -> list[Episode]:
        """Full-text search over episode summaries, most relevant first."""
        tsquery = func.plainto_tsquery(_FTS_DICTIONARY, query)
        rank = func.ts_rank(Episode.summary_tsv, tsquery)
        result = await self._db.execute(
            select(Episode)
            .where(Episode.summary_tsv.op("@@")(tsquery))
            .order_by(rank.desc(), Episode.happened_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
