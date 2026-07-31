"""Liveness health endpoint.

An ops/infra endpoint, deliberately version-independent: it is mounted at the
application root (not under ``/v1``) because probes must not care about the
business API version. It answers exactly one question: *is this process up and
serving requests?*

Design constraints (see ``CLAUDE.md`` §5 — Engineering bar):

- **Dependency-free (scalability).** A liveness probe MUST NOT touch the DB or any
  external dependency. If it did, a transient dependency blip would make the
  orchestrator (Cloud Run / k8s) kill and restart otherwise-healthy instances,
  amplifying an outage instead of containing it. "Can we serve traffic yet?"
  (dependency readiness) belongs in a separate future ``/readyz`` probe.
- **No sensitive data (security).** The endpoint is unauthenticated — probes carry
  no credentials — so it must never expose environment, debug flags, config
  values, or stack traces. Service name and version are safe (already public via
  the OpenAPI schema) and useful to confirm what is actually deployed.
- **Cheap and uncacheable (efficiency).** Probes hit constantly; the payload is
  tiny and fixed, the handler does no I/O, and ``no-store`` guarantees an
  intermediary never serves a stale "healthy" for a process that has since died.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from service import SERVICE_NAME, __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Liveness payload. Intentionally minimal — no config or runtime state."""

    status: str
    service: str
    version: str


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz(response: Response) -> HealthResponse:
    # Never let a proxy/CDN cache a health result.
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__)
