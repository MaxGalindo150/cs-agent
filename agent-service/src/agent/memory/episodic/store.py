"""Episodic memory store — dated events over PostgreSQL.

Semantic memory answers "what is true?"; episodic answers "what happened, and
when?". Mirrors Waku's ``SqliteEpisodeStore`` surface, with the same serverless
connection discipline as the semantic store (Database-held, short session per
call) and delegation to :class:`~agent.memory.repositories.EpisodeRepository`.

Retrieval blends relevance with recency, as in Waku: full-text rank first, most
recent first among matches, and a straight recency listing when the query has no
usable search terms at all.
"""

from __future__ import annotations

import re
from datetime import datetime

from agent.memory.db import Database
from agent.memory.repositories import EpisodeRepository

# Does the query carry anything worth searching on? Mirrors Waku's `_fts_query`
# guard, which returns "" for text with no usable tokens. Unlike Waku's
# `[a-zA-Z0-9]` we match unicode word characters, so accented Spanish terms
# ("años", "configuración") count as searchable (ADR-0002: content is Spanish).
_SEARCHABLE = re.compile(r"[^\W_]{2,}", re.UNICODE)


class PostgresEpisodeStore:
    """Waku-style episode store: call it without managing a session yourself."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, summary: str, happened_at: datetime) -> None:
        async with self._db.session() as session:
            await EpisodeRepository(session).add(happened_at, summary)

    async def search(self, query: str, top_k: int = 3) -> list[str]:
        """Relevance first (full text), most recent first among matches.

        A query with no usable terms falls back to plain recency rather than
        returning nothing — the same behaviour as Waku.
        """
        if not _SEARCHABLE.search(query):
            return await self.recent(top_k)
        async with self._db.session() as session:
            episodes = await EpisodeRepository(session).search(query, limit=top_k)
            return [f"({ep.happened_at:%Y-%m-%d}) {ep.summary}" for ep in episodes]

    async def recent(self, top_k: int = 3) -> list[str]:
        """The most recent episodes, formatted for injection."""
        async with self._db.session() as session:
            episodes = await EpisodeRepository(session).list_recent(limit=top_k)
            return [f"({ep.happened_at:%Y-%m-%d}) {ep.summary}" for ep in episodes]
