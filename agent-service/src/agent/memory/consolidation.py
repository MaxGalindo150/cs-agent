"""Consolidation — distilling one user's chats into durable memory (facts +
episodes). Ported from waku-agent's ``waku/memory/consolidation.py``.

Per-user batching is the direct translation of waku's single-user model:
waku has exactly one user, so "the whole chat_log" and "this user's messages"
are the same set. Here, with many users sharing the schema, the equivalent
unit is "one user's unconsolidated messages across all their sessions" —
every fact/episode is personal (docs/SECURITY.md §3), so consolidation must
always know whose.

Deliberately **not** run inline in the request path (CLAUDE.md §4/§9 — an
extra LLM call per turn would blow the latency/cost budget under Cloud Run
concurrency, the exact lesson ``agent/app.py::respond`` already documents).
Triggered externally, via ``service/worker``'s internal endpoint.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import anthropic
from anthropic.types import TextBlock

from agent.memory.db import Database
from agent.memory.repositories import (
    EpisodeRepository,
    FactRepository,
    SessionRepository,
)

SUMMARIZER_PROMPT = """\
You distill a customer support conversation into long-term memory about the customer.

From the exchanges below, extract:
1. durable facts about the customer, their preferences, or their situation —
   only things worth remembering in a month; skip chit-chat and one-offs.
2. one single-sentence episode summarizing what happened in this conversation.

Reply with ONLY this JSON:
{{"facts": [{{"subject": "<who/what>", "content": "<one sentence>"}}], \
"episode": "<one sentence>"}}

Exchanges:
{log}"""


async def consolidate_user_if_due(
    db: Database,
    client: anthropic.AsyncAnthropic,
    fast_model: str,
    every_n: int,
    user_id: str,
) -> int:
    """Consolidate one user's unconsolidated messages, if there are enough.

    Returns how many new facts were written. ``0`` covers three cases the
    caller cannot (and needn't) tell apart — not due yet, nothing worth
    keeping, or the summarizer failed — because in every case the messages
    stay unconsolidated and are retried on the next sweep; nothing is ever
    lost.
    """
    async with db.session() as session:
        messages = await SessionRepository(session).list_unconsolidated_for_user(
            user_id
        )
    if len(messages) < every_n * 2:  # each exchange = 2 rows (user + assistant)
        return 0

    log = "\n".join(f"{m.role}: {m.content}" for m in messages)
    try:
        response = await client.messages.create(
            model=fast_model,
            max_tokens=600,
            messages=[{"role": "user", "content": SUMMARIZER_PROMPT.format(log=log)}],
        )
        text = "".join(b.text for b in response.content if isinstance(b, TextBlock))
        distilled = json.loads(text[text.index("{") : text.rindex("}") + 1])
    except (anthropic.APIError, ValueError, json.JSONDecodeError):
        return 0  # never lose the log — it stays unconsolidated for next time

    new_facts = 0
    async with db.session() as session:
        fact_repo = FactRepository(session)
        for fact in distilled.get("facts", []):
            if fact.get("subject") and fact.get("content"):
                await fact_repo.add(
                    fact["subject"],
                    fact["content"],
                    source="consolidation",
                    user_id=user_id,
                )
                new_facts += 1
        if distilled.get("episode"):
            await EpisodeRepository(session).add(
                datetime.now(UTC), distilled["episode"], user_id=user_id
            )
        await SessionRepository(session).mark_consolidated([m.id for m in messages])

    return new_facts


async def consolidate_all_due_users(
    db: Database,
    client: anthropic.AsyncAnthropic,
    fast_model: str,
    every_n: int,
    batch_size: int,
    max_concurrency: int,
) -> dict[str, int]:
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

    async def _bounded(user_id: str) -> tuple[str, int]:
        async with semaphore:
            new_facts = await consolidate_user_if_due(
                db, client, fast_model, every_n, user_id
            )
        return user_id, new_facts

    results = await asyncio.gather(*(_bounded(user_id) for user_id in user_ids))
    return dict(results)
