"""Internal worker endpoints — never user-facing, never mounted under /v1.

Today: consolidation (agent/memory/consolidation.py). Triggered by an
external periodic caller (a compose cron sidecar in dev, Cloud Scheduler in
deploy — CLAUDE.md §4/§9), not by the request path itself.
"""

from __future__ import annotations

from service.worker.consolidate import router

__all__ = ["router"]
