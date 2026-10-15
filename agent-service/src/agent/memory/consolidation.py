"""Consolidation — distilling one user's chats into durable memory (facts +
episodes). Ported from waku-agent's ``waku/memory/consolidation.py``.

Per-user batching is the direct translation of waku's single-user model:
waku has exactly one user, so "the whole chat_log" and "this user's messages"
are the same set. Here, with many users sharing the schema, the equivalent
unit is "one user's unconsolidated messages across all their sessions" —
every fact/episode is personal (docs/SECURITY.md §3), so consolidation must
always know whose.

With a decision model (``decisions``, ADR-0004) two judgment calls bracket
the summarizer: a gate before it — is there anything in these exchanges
worth a memory pass at all? — and a per-fact filter after it, so only
durable, specific, not-yet-known facts are written. Both run in the worker,
off the request path, with the same fallback as everywhere: no decider, or
a failed call, and the pass runs exactly as before.

Deliberately **not** run inline in the request path (CLAUDE.md §4/§9 — an
extra LLM call per turn would blow the latency/cost budget under Cloud Run
concurrency, the exact lesson ``agent/app.py::respond`` already documents).
Triggered externally, via ``service/worker``'s internal endpoint.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import anthropic
from anthropic.types import TextBlock

from agent.decide.sites import Decisions
from agent.memory.db import Database
from agent.memory.repositories import (
    EpisodeRepository,
    FactRepository,
    SessionRepository,
)
from agent.observability import Observer
from agent.prompts import load_prompt


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """What one user's consolidation pass wrote — 0/0 covers "not due yet",
    "nothing worth keeping", and "summarizer failed" alike (see
    ``consolidate_user_if_due``)."""

    facts: int = 0
    episodes: int = 0
    skipped: bool = False
    """The decision model judged these exchanges not worth a memory pass:
    they were marked consolidated without calling the summarizer."""
    dropped_facts: int = 0
    """Candidate facts the summarizer produced that the decision model
    rejected as not durable, not specific, or already known."""


SUMMARIZER_PROMPT = load_prompt("internal/memory_summarizer")


async def consolidate_user_if_due(
    db: Database,
    client: anthropic.AsyncAnthropic,
    fast_model: str,
    every_n: int,
    user_id: str,
    decisions: Decisions | None = None,
    notify: Observer | None = None,
) -> ConsolidationResult:
    """Consolidate one user's unconsolidated messages, if there are enough.

    Returns how many new facts/episodes were written. ``ConsolidationResult()``
    (0/0) covers three cases the caller cannot (and needn't) tell apart — not
    due yet, nothing worth keeping, or the summarizer failed — because in
    every case the messages stay unconsolidated and are retried on the next
    sweep; nothing is ever lost.
    """
    async with db.session() as session:
        messages = await SessionRepository(session).list_unconsolidated_for_user(
            user_id
        )
    if len(messages) < every_n * 2:  # each exchange = 2 rows (user + assistant)
        return ConsolidationResult()

    log = "\n".join(f"{m.role}: {m.content}" for m in messages)
    judge = decisions or Decisions(None)

    gate = await judge.consolidation_gate(log, notify)
    if not gate.proceed:
        # Nothing durable here (greetings, tests, chit-chat): mark the rows
        # consolidated so they are not re-judged every sweep, write nothing.
        async with db.session() as session:
            await SessionRepository(session).mark_consolidated([m.id for m in messages])
        return ConsolidationResult(skipped=True)

    try:
        response = await client.messages.create(
            model=fast_model,
            max_tokens=600,
            messages=[{"role": "user", "content": SUMMARIZER_PROMPT.format(log=log)}],
        )
        text = "".join(b.text for b in response.content if isinstance(b, TextBlock))
        distilled = json.loads(text[text.index("{") : text.rindex("}") + 1])
        facts = distilled.get("facts", [])
        episode = distilled.get("episode")
        if not isinstance(facts, list) or not all(isinstance(f, dict) for f in facts):
            raise ValueError("malformed 'facts' shape")
        if episode is not None and not isinstance(episode, str):
            raise ValueError("malformed 'episode' shape")
    except (anthropic.APIError, ValueError, json.JSONDecodeError):
        # Treated the same as invalid JSON — an unusable shape is as
        # unusable as unparseable text, and must not abort the rest of the
        # sweep (this only affects the one user whose response is bad).
        return ConsolidationResult()  # never lose the log — retried next time

    candidates = [
        f
        for f in facts
        if isinstance(f.get("subject"), str)
        and isinstance(f.get("content"), str)
        and f["subject"]
        and f["content"]
    ]
    dropped = 0
    if candidates and judge.enabled:
        # What is already known about these subjects, so the filter can
        # reject a restatement. One short session, closed before the call.
        async with db.session() as session:
            repo = FactRepository(session)
            existing: list[str] = []
            for subject in {str(f["subject"]) for f in candidates}:
                rows = await repo.list_by_subject(subject, user_id, limit=10)
                existing += [f"[{r.subject}] {r.content}" for r in rows]
        selection = await judge.fact_select(candidates, existing, notify)
        candidates, dropped = selection.kept, selection.dropped

    new_facts = 0
    new_episodes = 0
    async with db.session() as session:
        fact_repo = FactRepository(session)
        for fact in candidates:
            subject = fact.get("subject")
            content = fact.get("content")
            # isinstance, not just truthy — a dict shape is already confirmed
            # above, but subject/content could still be a non-string truthy
            # value (an int, a list); FactRepository.add expects str, and
            # this loop runs outside the parse try/except, so a bad value
            # here would otherwise crash the whole sweep, not just this user.
            if (
                isinstance(subject, str)
                and isinstance(content, str)
                and subject
                and content
            ):
                await fact_repo.add(
                    subject,
                    content,
                    source="consolidation",
                    user_id=user_id,
                )
                new_facts += 1
        if episode:
            await EpisodeRepository(session).add(
                datetime.now(UTC), episode, user_id=user_id
            )
            new_episodes += 1
        await SessionRepository(session).mark_consolidated([m.id for m in messages])

    return ConsolidationResult(
        facts=new_facts, episodes=new_episodes, dropped_facts=dropped
    )


async def consolidate_all_due_users(
    db: Database,
    client: anthropic.AsyncAnthropic,
    fast_model: str,
    every_n: int,
    batch_size: int,
    max_concurrency: int,
    decisions: Decisions | None = None,
    notify: Observer | None = None,
) -> dict[str, ConsolidationResult]:
    """Sweep users with pending unconsolidated messages, oldest-waiting first.

    Bounded on two axes so one sweep can never blow up into an
    hours-long request as the user base grows:

    - ``batch_size`` caps how many users a single call takes on — the rest
      wait for the next sweep (the external trigger runs this periodically,
      see ``service/worker``), so a huge backlog drains over several sweeps
      instead of one giant one.
    - ``max_concurrency`` runs up to that many users' consolidation
      concurrently (each with its own short DB sessions — never one held
      across the LLM call, per-user, per CLAUDE.md §3), so the sweep isn't
      needlessly serialized behind LLM latency.

    Called by the internal worker endpoint (``service/worker``), never the
    request path — see the module docstring for why.
    """
    async with db.session() as session:
        user_ids = await SessionRepository(session).list_unconsolidated_user_ids(
            limit=batch_size
        )

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded(user_id: str) -> tuple[str, ConsolidationResult]:
        async with semaphore:
            result = await consolidate_user_if_due(
                db, client, fast_model, every_n, user_id, decisions, notify
            )
        return user_id, result

    results = await asyncio.gather(*(_bounded(user_id) for user_id in user_ids))
    return dict(results)
