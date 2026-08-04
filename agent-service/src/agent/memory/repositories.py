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


def _owner_filter(column: Any, user_id: str | None) -> Any:
    """Every fact/episode query must filter by owner — there is no "no filter"
    mode (docs/SECURITY.md §3). ``user_id=None`` filters for rows with no
    owner (``IS NULL``), it never means "match every user's rows"."""
    return column.is_(None) if user_id is None else column == user_id


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

    async def mark_escalated(self, session_id: uuid.UUID, reason: str) -> bool:
        """Flag a session for human follow-up. Idempotent: only writes if not
        already escalated (the ``WHERE`` guards it), so a tool can tell the
        model "already escalated" from the return value alone, with no
        separate read. Returns ``False`` for an unknown session id too —
        there's no row to match either way."""
        result = await self._db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.escalated_at.is_(None),
            )
            .values(escalated_at=func.now(), escalation_reason=reason)
        )
        return cast(CursorResult[Any], result).rowcount > 0

    async def set_suspended_tool_use(
        self, session_id: uuid.UUID, payload: dict[str, Any]
    ) -> None:
        """First write for a new suspension (agent/tools/registry.py's
        Tool.suspends). Nothing else can race to set this at the same moment a
        turn suspends — the write path that calls this is the only one that
        ever does, right after `run_loop` returns with `LoopResult.suspended`
        set."""
        await self._db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(suspended_tool_use=payload)
        )

    async def peek_suspended_tool_use(
        self, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Read-only: whether a suspension is pending, without consuming it.
        Callers must decide an incoming request actually resolves it (a
        matching `choice_id`, or any free text) BEFORE calling
        `claim_suspended_tool_use` — a mere read must never clear it, or a
        stale/garbage `choice_id` with no accompanying text would silently
        destroy a still-live suspension."""
        return await self._db.scalar(
            select(ChatSession.suspended_tool_use).where(ChatSession.id == session_id)
        )

    async def claim_suspended_tool_use(
        self, session_id: uuid.UUID, tool_use_id: str
    ) -> bool:
        """Atomically clear the pending suspension iff it's still this exact
        one — same idempotency shape as `mark_escalated` (the guard lives in
        the `WHERE`, not a separate read-then-write), keyed on `tool_use_id`
        instead of an `IS NULL` check. Returns ``False`` if it was already
        claimed by a concurrent request (double submit, a retried request) or
        superseded by a newer suspension — the caller must not resume or
        persist anything in that case, only treat it as already handled."""
        result = await self._db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.suspended_tool_use["tool_use_id"].astext == tool_use_id,
            )
            .values(suspended_tool_use=None)
        )
        return cast(CursorResult[Any], result).rowcount > 0

    async def mark_choice_resolved(
        self, session_id: uuid.UUID, tool_use_id: str, resolved_option_id: str | None
    ) -> bool:
        """Patch the suspended half-turn's persisted `choice` segment so any
        reload (this tab or another) renders it resolved — settled buttons,
        not live/re-clickable ones. This is what shrinks how often a stale
        click can even happen in the first place.

        ``resolved_option_id`` is ``None`` when the customer typed free text
        instead of clicking: the question is still settled (no more live
        buttons), just without a specific option to highlight — the renderer
        tells these apart via ``resolved`` (always ``True`` here) vs whether
        ``resolvedOptionId`` is present at all."""
        row = await self._db.scalar(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
                ChatMessage.meta["tool_use_id"].astext == tool_use_id,
            )
            .order_by(ChatMessage.seq.desc())
            .limit(1)
        )
        if row is None or not row.meta or not row.meta.get("segments"):
            return False
        segments = list(row.meta["segments"])
        if not segments or segments[-1].get("type") != "choice":
            return False
        segments[-1] = {**segments[-1], "resolved": True}
        if resolved_option_id is not None:
            segments[-1]["resolvedOptionId"] = resolved_option_id
        # Reassign the whole dict: `meta` is a plain JSONB column (no
        # MutableDict wrapper), so an in-place mutation wouldn't be tracked
        # and would silently fail to flush.
        row.meta = {**row.meta, "segments": segments}
        await self._db.flush()
        return True

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

    async def list_unconsolidated_user_ids(self, limit: int | None = None) -> list[str]:
        """Users with unconsolidated messages waiting, oldest-waiting first —
        anonymous sessions (``user_id IS NULL``) are excluded: there is no
        owner to attribute a fact/episode to (docs/SECURITY.md §3), so their
        messages are never consolidated, only ever session-local context.

        ``limit`` bounds how many users a single sweep takes on — without it,
        a sweep over many thousands of due users would run one LLM call after
        another inside a single request (agent/memory/consolidation.py). The
        oldest-first order means a capped sweep still makes fair progress
        instead of starving the same tail of users every time.
        """
        query = (
            select(ChatSession.user_id)
            .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatMessage.consolidated.is_(False),
                ChatSession.user_id.is_not(None),
            )
            .group_by(ChatSession.user_id)
            .order_by(func.min(ChatMessage.seq))
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self._db.execute(query)
        return [uid for uid in result.scalars().all() if uid is not None]

    async def list_unconsolidated_for_user(
        self, user_id: str, limit: int = 500
    ) -> list[ChatMessage]:
        """One user's unconsolidated messages across all their sessions,
        oldest first. ``seq`` is a single global identity sequence (not
        per-session), so ordering by it still gives correct chronological
        order across a user's multiple conversations."""
        result = await self._db.execute(
            select(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatMessage.consolidated.is_(False),
                ChatSession.user_id == user_id,
            )
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
        user_id: str | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Fact:
        """Store a fact, optionally with its embedding (ADR-0003).

        ``embedding`` is left NULL when embedding is unavailable — the fact is
        still written and stays findable by full text. ``user_id`` is who the
        fact is about (docs/SECURITY.md §3) — every fact is personal, so a
        future write path must always supply it.
        """
        fact = Fact(
            subject=subject,
            content=content,
            source=source,
            user_id=user_id,
            embedding=embedding,
            embedding_model=embedding_model if embedding is not None else None,
        )
        self._db.add(fact)
        await self._db.flush()
        return fact

    async def list_by_subject(
        self, subject: str, user_id: str | None, limit: int = 50
    ) -> list[Fact]:
        result = await self._db.execute(
            select(Fact)
            .where(Fact.subject == subject, _owner_filter(Fact.user_id, user_id))
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search(
        self, query: str, user_id: str | None, limit: int = 20
    ) -> list[Fact]:
        """Full-text search, most relevant first, scoped to one owner.

        ``plainto_tsquery`` takes a plain phrase (no operator syntax), so
        untrusted text can be passed straight through — it cannot inject query
        operators.
        """
        tsquery = func.plainto_tsquery(_FTS_DICTIONARY, query)
        rank = func.ts_rank(Fact.content_tsv, tsquery)
        result = await self._db.execute(
            select(Fact)
            .where(
                Fact.content_tsv.op("@@")(tsquery), _owner_filter(Fact.user_id, user_id)
            )
            .order_by(rank.desc(), Fact.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_semantic(
        self, embedding: list[float], user_id: str | None, limit: int = 20
    ) -> list[Fact]:
        """Nearest facts by meaning — cosine distance over the HNSW index,
        scoped to one owner.

        Ranking happens entirely in Postgres (``<=>``); the stored vectors are
        never loaded into Python. Rows without an embedding are excluded rather
        than sorted last: a NULL distance would otherwise pollute the ordering.
        """
        result = await self._db.execute(
            select(Fact)
            .where(Fact.embedding.is_not(None), _owner_filter(Fact.user_id, user_id))
            .order_by(Fact.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update(
        self,
        fact_id: uuid.UUID,
        user_id: str | None,
        content: str,
        subject: str | None = None,
    ) -> bool:
        """Correct a fact's content (and optionally its subject).

        Scoped by owner in the same statement as the id match — never two
        separate checks — so there is no window where an id belonging to
        another user could be updated (docs/SECURITY.md §3).
        """
        values: dict[str, Any] = {"content": content}
        if subject is not None:
            values["subject"] = subject
        result = await self._db.execute(
            update(Fact)
            .where(Fact.id == fact_id, _owner_filter(Fact.user_id, user_id))
            .values(**values)
        )
        return cast(CursorResult[Any], result).rowcount > 0

    async def delete(self, fact_id: uuid.UUID, user_id: str | None) -> bool:
        """Forget a fact. Scoped by owner — see `update` for why."""
        result = await self._db.execute(
            delete(Fact).where(Fact.id == fact_id, _owner_filter(Fact.user_id, user_id))
        )
        return cast(CursorResult[Any], result).rowcount > 0


class EpisodeRepository:
    """Episodic memory: dated summaries, retrieved by recency or full text."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def add(
        self, happened_at: datetime, summary: str, user_id: str | None = None
    ) -> Episode:
        """``user_id`` is who the episode is about (docs/SECURITY.md §3) —
        every episode is personal, so a future write path must always supply
        it."""
        episode = Episode(happened_at=happened_at, summary=summary, user_id=user_id)
        self._db.add(episode)
        await self._db.flush()
        return episode

    async def list_recent(self, user_id: str | None, limit: int = 20) -> list[Episode]:
        result = await self._db.execute(
            select(Episode)
            .where(_owner_filter(Episode.user_id, user_id))
            .order_by(Episode.happened_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search(
        self, query: str, user_id: str | None, limit: int = 20
    ) -> list[Episode]:
        """Full-text search over episode summaries, most relevant first,
        scoped to one owner."""
        tsquery = func.plainto_tsquery(_FTS_DICTIONARY, query)
        rank = func.ts_rank(Episode.summary_tsv, tsquery)
        result = await self._db.execute(
            select(Episode)
            .where(
                Episode.summary_tsv.op("@@")(tsquery),
                _owner_filter(Episode.user_id, user_id),
            )
            .order_by(rank.desc(), Episode.happened_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, episode_id: uuid.UUID, user_id: str | None) -> bool:
        """Forget an episode. Scoped by owner in the same statement as the id
        match (docs/SECURITY.md §3) — no separate check to get out of sync."""
        result = await self._db.execute(
            delete(Episode).where(
                Episode.id == episode_id, _owner_filter(Episode.user_id, user_id)
            )
        )
        return cast(CursorResult[Any], result).rowcount > 0
