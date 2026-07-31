"""Contract tests for the liveness endpoint (`GET /healthz`).

Level 1 (deterministic, no network) per ``CLAUDE.md`` §8. These lock the
contract that ops probes and load balancers depend on, so a refactor can't
silently change the status code, body shape, or caching behaviour.
"""

from __future__ import annotations

import httpx

from service import SERVICE_NAME, __version__


async def test_healthz_returns_ok_contract(client: httpx.AsyncClient) -> None:
    resp = await client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": __version__,
    }


async def test_healthz_is_not_cacheable(client: httpx.AsyncClient) -> None:
    # A cached "healthy" could outlive a dead process; probes must never cache.
    resp = await client.get("/healthz")

    assert resp.headers["cache-control"] == "no-store"


async def test_healthz_exposes_no_extra_fields(client: httpx.AsyncClient) -> None:
    # Security: an unauthenticated liveness probe must not leak environment,
    # debug flags, config, or anything beyond the three contract fields.
    resp = await client.get("/healthz")

    assert set(resp.json().keys()) == {"status", "service", "version"}
