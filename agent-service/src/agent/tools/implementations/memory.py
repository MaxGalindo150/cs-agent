"""Memory self-management — the agent can search, correct, or forget what it
remembers about the caller. Ported from waku-agent's `manage_memory`
(waku/tools/memory_admin.py), onto Postgres facts/episodes instead of SQLite.

No "create" action, unlike a naive port might assume: a fact or episode is
only ever created by consolidation (agent/memory/__init__.py — not yet ported
here), never directly from a tool call. Episodes are historical — only facts
can be corrected, matching waku's own rule.

Identity-gated (`requires_identity=True`): every operation is scoped to the
caller's own `user_id` (docs/SECURITY.md §3). `update`/`delete` filter by id
*and* owner in the same statement (agent/memory/repositories.py), so an id
that happens to belong to another user is invisible, not just refused.
"""

from __future__ import annotations

import uuid

from agent.memory.db import Database
from agent.memory.repositories import EpisodeRepository, FactRepository
from agent.tools.context import ToolContext
from agent.tools.registry import Tool

_SEARCH_LIMIT = 8


def make_manage_memory_tool(db: Database) -> Tool:
    async def manage_memory(
        ctx: ToolContext,
        action: str = "",
        kind: str = "fact",
        id: str = "",
        query: str = "",
        content: str = "",
        subject: str = "",
    ) -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
        user_id = ctx.principal.user_id
        action = action.lower()
        kind = kind.lower() or "fact"

        async with db.session() as session:
            if action == "search":
                if kind == "episode":
                    episodes = (
                        await EpisodeRepository(session).search(
                            query, user_id, limit=_SEARCH_LIMIT
                        )
                        if query
                        else await EpisodeRepository(session).list_recent(
                            user_id, limit=_SEARCH_LIMIT
                        )
                    )
                    if not episodes:
                        return "no episodes"
                    return "\n".join(
                        f"#{e.id} ({e.happened_at:%Y-%m-%d}) {e.summary}"
                        for e in episodes
                    )
                facts = await FactRepository(session).search(
                    query, user_id, limit=_SEARCH_LIMIT
                )
                if not facts:
                    return "no matching facts"
                return "\n".join(f"#{f.id} [{f.subject}] {f.content}" for f in facts)

            if action not in ("update", "delete"):
                return "action must be one of: search, update, delete"

            fact_or_episode_id = _parse_id(id)
            if fact_or_episode_id is None:
                return f"'{id}' is not a valid memory id — search first to get one."

            if action == "update":
                if kind != "fact":
                    return "Only facts can be updated (episodes are historical)."
                if not content:
                    # Unlike subject (optional — `subject or None` leaves it
                    # untouched), content has no "leave as-is" meaning: an
                    # update IS a new content. Reject rather than silently
                    # wiping the fact to an empty string.
                    return "update needs content — say what the fact should now say."
                ok = await FactRepository(session).update(
                    fact_or_episode_id, user_id, content, subject or None
                )
                return f"Updated fact #{id}." if ok else f"No fact with id {id}."

            if kind == "episode":
                ok = await EpisodeRepository(session).delete(
                    fact_or_episode_id, user_id
                )
                return f"Deleted episode #{id}." if ok else f"No episode with id {id}."
            ok = await FactRepository(session).delete(fact_or_episode_id, user_id)
            return f"Deleted fact #{id}." if ok else f"No fact with id {id}."

    return Tool(
        name="manage_memory",
        description=(
            "Search, correct, or delete what you remember about this user (facts and "
            "episodes). ALWAYS search first to get an id, then update or delete that "
            "id. Use when the user says something you remember is wrong or asks you "
            "to forget it. You cannot create new facts or episodes with this tool — "
            "only correct or remove what already exists."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "update", "delete"],
                },
                "kind": {
                    "type": "string",
                    "enum": ["fact", "episode"],
                    "description": "what to operate on — defaults to 'fact'",
                },
                "id": {
                    "type": "string",
                    "description": "memory id (from a prior search) — required "
                    "for update/delete",
                },
                "query": {
                    "type": "string",
                    "description": "keywords for search",
                },
                "content": {
                    "type": "string",
                    "description": "new text, for update",
                },
                "subject": {
                    "type": "string",
                    "description": "optional new subject, for a fact update",
                },
            },
            "required": ["action"],
        },
        fn=manage_memory,
        requires_identity=True,
    )


def _parse_id(raw: str) -> uuid.UUID | None:
    """The model passes ids as plain strings (JSON has no UUID type); a
    malformed one is a model mistake, not a server error."""
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None
