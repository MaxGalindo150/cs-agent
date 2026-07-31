"""Memory facade — the pillars behind one small interface (mirrors Waku).

    procedural  SKILL.md files       how to act        (later — agent/skills, §9)
    semantic    facts table (FTS)    what is durably true
    episodic    episodes table       what happened, when

Plus the agents that manage them:
    retrieval_gate   decides IF a turn needs memory   (hero moment #1)
    consolidation    distils chats into facts         (later — not yet ported)

Provider- and transport-neutral by construction (CLAUDE.md §4): nothing here
imports ``service``, and the facade never reads the service ``Settings`` object.
Its tuning is injected as a small :class:`MemoryConfig`, the same way the
transport injects a ``DatabaseConfig`` — the brain depends on the abstraction,
not the concretion. See ADR-0002 (storage) and ADR-0003 (pgvector, pending).

Connection discipline (CLAUDE.md §3): the facade holds a :class:`Database`, not
a live session. The one method that mixes an LLM call with the store —
``gated_retrieve`` — runs the gate first (no DB), and only *then* opens a short
session for the search. The LLM call and the DB session never overlap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from agent.memory.db import Database
from agent.memory.embeddings import Embedder
from agent.memory.episodic.store import PostgresEpisodeStore
from agent.memory.procedural.loader import SkillLoader
from agent.memory.repositories import SessionRepository
from agent.memory.retrieval_gate import should_retrieve
from agent.memory.semantic.store import PostgresFactStore
from agent.observability import Observer

# Skills live at the project root's skills/ dir (Waku's layout). Our package
# sits one level deeper under src/agent/, so it's parents[3] (agent-service/),
# where Waku's is parents[2].
REPO_SKILLS = Path(__file__).resolve().parents[3] / "skills"


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """Tuning knobs for the memory facade, injected by the transport.

    ``fast_model`` is the cheap model that answers the retrieval gate's single
    yes/no question (CLAUDE.md maps this to ``ANTHROPIC_FAST_MODEL``).
    """

    fast_model: str
    retrieval_top_k: int = 4
    episode_top_k: int = 3


class Memory:
    def __init__(
        self,
        db: Database,
        client: AsyncAnthropic,
        config: MemoryConfig,
        embedder: Embedder | None = None,
    ) -> None:
        self._db = db
        self._client = client
        self._config = config
        # With no embedder, semantic memory degrades to full-text search — the
        # service still runs, just without paraphrase matching (ADR-0003 §7).
        self.facts = PostgresFactStore(db, embedder)
        self.episodes = PostgresEpisodeStore(db)
        # Repo skills only for now. Waku also scans a user-home dir
        # (WAKU_HOME/skills) for installed/agent-authored skills; on serverless
        # there is no such home, so that path lands with its own decision later.
        self.skills = SkillLoader([REPO_SKILLS])

    # ---- retrieval (gated — see retrieval_gate.py for why) -----------------
    async def gated_retrieve(self, message: str, notify: Observer | None = None) -> str:
        """Fetch relevant memory for a turn — but only if the gate says to.

        The gate is one cheap LLM call and touches no DB; the search that
        follows opens a short session and closes it. They run in sequence, never
        overlapping, so no connection is ever held across the LLM call.
        """
        retrieve, query, reason = await should_retrieve(
            self._client, self._config.fast_model, message
        )
        if notify:
            notify(
                "gate",
                {"decision": "retrieve" if retrieve else "skip", "reason": reason},
            )
        if not retrieve:
            return ""
        found = await self.facts.search(query, self._config.retrieval_top_k)
        found += await self.episodes.search(query, self._config.episode_top_k)
        return "\n".join(found)

    # ---- procedural --------------------------------------------------------
    def matching_skills(self, message: str) -> str:
        """Procedural memory: the bodies of any SKILL.md policies whose
        name+description overlaps this message (progressive disclosure). Empty
        when nothing matches — or when the skills/ dir has no skills yet."""
        matched = self.skills.match(message)
        return "\n\n".join(f"### {s.name}\n{s.body}" for s in matched)

    # ---- sessions & chat log ----------------------------------------------
    # In Waku these live on the facade (they are the raw log consolidation reads
    # from, not a memory pillar). Adapted to our first-class UUID sessions
    # (agent/memory/models.py) — sessions are created explicitly, not implied.
    async def create_session(
        self, title: str | None = None, user_id: str | None = None
    ) -> uuid.UUID:
        """Create a new conversation row and return its id.

        Sessions are explicit here (not implied by the first message), so the
        transport mints one for a 'new chat' and hands the id back to the client
        to continue. ``chat_messages`` FKs to this row, so it must exist before
        the turn is persisted.

        ``user_id`` is a plain string, never ``agent.identity.Principal`` — the
        memory facade stays decoupled from the identity type (CLAUDE.md §4);
        the caller (``Agent.start_session``) unwraps it.
        """
        async with self._db.session() as session:
            row = await SessionRepository(session).create_session(title, user_id)
        return row.id

    async def log_chat(
        self,
        user_message: str,
        reply: str,
        session_id: uuid.UUID,
        source: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Append one full turn (user + assistant) in a single short transaction.

        ``source`` (the input channel) tags both rows, as in Waku. Per-turn
        telemetry (gate decision, latency, tools) rides on the assistant row's
        ``meta`` so a reopened thread can rebuild the turn.
        """
        async with self._db.session() as session:
            repo = SessionRepository(session)
            await repo.append_message(session_id, "user", user_message, source=source)
            await repo.append_message(
                session_id, "assistant", reply, source=source, meta=meta
            )

    async def session_history(self, session_id: uuid.UUID) -> list[tuple[str, str]]:
        """The (user, assistant) exchanges of a past session, in order — used to
        reload working memory when switching back to a conversation."""
        async with self._db.session() as session:
            messages = await SessionRepository(session).list_messages(session_id)
            pairs: list[tuple[str, str]] = []
            pending: str | None = None
            for message in messages:
                if message.role == "user":
                    pending = message.content
                elif pending is not None:
                    pairs.append((pending, message.content))
                    pending = None
            return pairs

    async def list_sessions(self, limit: int = 50) -> list[dict[str, object]]:
        """One row per conversation, most recently active first — the order a
        chat sidebar wants."""
        async with self._db.session() as session:
            sessions = await SessionRepository(session).list_sessions(limit)
            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "created_at": s.created_at,
                    "last_activity_at": s.last_activity_at,
                }
                for s in sessions
            ]
