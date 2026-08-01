"""Consolidation trigger — POST /internal/consolidate.

Not a business route: guarded by a shared-secret header (`X-Worker-Token`),
never called by the frontend or the chat endpoints. Meant to be hit
periodically by something external (a compose cron sidecar locally, Cloud
Scheduler in deploy) — the request path itself never runs consolidation
inline (agent/memory/consolidation.py explains why).
"""

from __future__ import annotations

import secrets

import structlog
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, Header, HTTPException, status

from agent.memory.consolidation import ConsolidationResult, consolidate_all_due_users
from agent.memory.db import Database
from service.core.agent import get_database
from service.core.config import Settings, get_settings
from service.core.llm import get_llm_client

log = structlog.get_logger()

router = APIRouter(tags=["worker"])


def _require_worker_token(
    settings: Settings = Depends(get_settings),
    x_worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
) -> None:
    """Fail closed: an unset `internal_worker_token` (its default) can never
    match a supplied header, so an unconfigured deployment refuses every call
    rather than silently accepting one (docs/SECURITY.md). Compared with
    `secrets.compare_digest` — a plain `!=` leaks how many leading characters
    of a guessed token were correct via response-timing differences."""
    if not settings.internal_worker_token or not secrets.compare_digest(
        x_worker_token or "", settings.internal_worker_token
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid worker token")


@router.post(
    "/internal/consolidate",
    dependencies=[Depends(_require_worker_token)],
)
async def consolidate(
    db: Database = Depends(get_database),
    client: AsyncAnthropic = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, ConsolidationResult]:
    """Sweep up to a batch of due users; returns new facts/episodes written
    per user_id (0/0 for a user swept but not yet due). A backlog larger than
    the batch is left for the next periodic trigger — see agent/memory/
    consolidation.py for why this is bounded rather than exhaustive."""
    results = await consolidate_all_due_users(
        db,
        client,
        settings.anthropic_fast_model,
        settings.consolidate_every,
        settings.consolidate_batch_size,
        settings.consolidate_concurrency,
    )
    log.info(
        "consolidation.swept",
        users_checked=len(results),
        new_facts=sum(r.facts for r in results.values()),
        new_episodes=sum(r.episodes for r in results.values()),
    )
    return results
