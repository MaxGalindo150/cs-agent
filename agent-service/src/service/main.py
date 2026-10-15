"""FastAPI application entrypoint for the agent service.

Two deliberate structural choices:

- **Application factory (`create_app`).** Building the app inside a function lets
  tests construct a fresh, isolated instance (and override dependencies) without
  import-time side effects leaking between tests.
- **Lifespan context manager.** The modern replacement for the deprecated
  ``@app.on_event("startup"/"shutdown")`` hooks — one place for process-level
  setup and teardown, with a clean ``yield`` boundary.

Nothing here calls the LLM or the DB: this module wires the process. Business
routers are mounted as they land.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from anthropic import APIError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.tools import build_registry
from agent.tools.implementations.propose_skill import make_propose_skill_tool
from service import SERVICE_NAME, __version__
from service.api.errors import handle_provider_error
from service.api.health import router as health_router
from service.api.v1.router import router as v1_router
from service.core.agent import (
    build_database,
    build_decider,
    build_embedder,
    build_service_agent,
)
from service.core.config import Settings, get_settings
from service.core.host_token import FirebaseTokenVerifier
from service.core.limits import MaxBodySizeMiddleware
from service.core.llm import build_anthropic_client
from service.core.migrations import upgrade_to_head
from service.core.tooling import build_bnpl_client
from service.worker import router as worker_router


def _configure_logging(settings: Settings) -> None:
    """Configure structlog once, driven by config.

    JSON output outside local dev (machine-parseable for Cloud Logging), and a
    human-readable console renderer in dev. Kept idempotent-friendly:
    ``cache_logger_on_first_use`` avoids reconfiguring loggers per request.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.is_development
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Process startup/shutdown. Validating config here means a misconfigured
    service fails fast at boot instead of serving a false 'healthy'."""
    settings = get_settings()
    _configure_logging(settings)
    log = structlog.get_logger()
    log.info(
        "service.start",
        service=SERVICE_NAME,
        version=__version__,
        environment=settings.environment,
    )
    # Bring the schema to head before anything serves. Dev convenience; off in
    # prod (RUN_MIGRATIONS_ON_STARTUP=false) where migrations are a deploy step.
    if settings.run_migrations_on_startup:
        log.info("migrations.upgrade.start")
        await upgrade_to_head()
        log.info("migrations.upgrade.done")
    # Build the LLM client once and reuse it — a per-request client would leak
    # connections. Routes reach it via the get_llm_client dependency.
    app.state.llm = build_anthropic_client(settings)
    app.state.bnpl = build_bnpl_client(settings)
    # Verifies the embedded widget host's Firebase tokens; built once so its
    # cache of Google's signing keys is shared (service/core/host_token.py).
    app.state.host_verifier = FirebaseTokenVerifier(settings.firebase_project_id)
    # Cashea's merchant API, called with an aliado's own token (identity
    # lookup at sign-in; the merchant tools later). None when unconfigured.
    app.state.merchant_api = (
        httpx.AsyncClient(base_url=settings.merchant_api_url, timeout=5.0)
        if settings.merchant_api_url
        else None
    )
    # Durable stores for memory & sessions (pooled) — built before the registry
    # since manage_memory (agent/tools/implementations/memory.py) needs it.
    app.state.db = build_database(settings)
    # Assemble the tool registry once, bound to the process-wide BNPL client
    # and the memory database.
    app.state.registry = build_registry(
        app.state.bnpl, app.state.db, app.state.merchant_api
    )
    # The assembled Agent — the brain the request path calls. Built once;
    # nothing conversation-specific lives on it.
    app.state.embedder = build_embedder(settings)
    # The harness's decision model (ADR-0004): one client shared by every
    # decision site, or None when TYPESAFE_API_KEY is empty.
    app.state.decider = build_decider(settings)
    app.state.agent = build_service_agent(
        settings,
        client=app.state.llm,
        db=app.state.db,
        tools=app.state.registry,
        embedder=app.state.embedder,
        decider=app.state.decider,
    )
    if settings.skill_proposals_enabled:
        # Registered after the Agent exists because the proposal gate needs
        # its memory (the conversation, the skill catalogue) and its decision
        # model. Flag-gated: see Settings.skill_proposals_enabled.
        app.state.registry.register(
            make_propose_skill_tool(app.state.agent.memory, app.state.agent.decisions)
        )
    log.info(
        "decisions.configured",
        enabled=app.state.decider is not None,
        model=settings.jev_model if app.state.decider else None,
        threshold=settings.jev_confidence_threshold,
        skill_proposals=settings.skill_proposals_enabled,
    )
    try:
        yield
    finally:
        await app.state.llm.close()
        await app.state.bnpl.aclose()
        if app.state.merchant_api is not None:
            await app.state.merchant_api.aclose()
        if app.state.decider is not None:
            await app.state.decider.aclose()
        await app.state.embedder.aclose()
        await app.state.db.dispose()
        log.info("service.stop", service=SERVICE_NAME)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=__version__,
        lifespan=lifespan,
        # Interactive docs only in dev — smaller attack/info-disclosure surface
        # in deployed environments. Flip per-env if a staging playground is wanted.
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
    )

    # Registered first so CORS (added next) ends up outermost — Starlette's
    # add_middleware stack is LIFO, so the *last* middleware added wraps
    # everything else. If this were outermost instead, its 413 short-circuit
    # would bypass CORSMiddleware entirely: a cross-origin browser client
    # would see an opaque CORS failure instead of a readable 413 JSON body.
    # Still rejects an oversized body before routing/request parsing ever run.
    app.add_middleware(MaxBodySizeMiddleware)

    # The browser widget calls this API cross-origin. Origins are an explicit
    # allowlist from config — never "*", which combined with credentials would
    # defeat the same-origin protection entirely.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Provider failures become a clean 502, never a raw stack trace.
    app.add_exception_handler(APIError, handle_provider_error)

    app.include_router(health_router)
    app.include_router(v1_router)
    app.include_router(worker_router)

    return app


app = create_app()
