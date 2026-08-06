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

import structlog
from anthropic import APIError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.tools import build_merchant_registry, build_registry
from service import SERVICE_NAME, __version__
from service.api.errors import handle_provider_error
from service.api.health import router as health_router
from service.api.v1.router import router as v1_router
from service.core.agent import (
    build_database,
    build_embedder,
    build_service_agent,
)
from service.core.config import Settings, get_settings
from service.core.limits import MaxBodySizeMiddleware
from service.core.llm import build_anthropic_client
from service.core.migrations import upgrade_to_head
from service.core.tooling import build_bnpl_client, build_merchant_client
from service.worker import router as worker_router

# ── Merchant persona ──
# The buyer ("Cheo") soul is a constant in agent/runtime/session.py. The
# merchant soul lives here so the merchant persona can evolve alongside the
# merchant tools without touching the brain-side session module.
MERCHANT_SOUL = """\
You are Cheo, a customer-support agent for Cashea's merchant partners (aliados).
You help merchants with their orders, payments, conciliation, payouts, invoices,
2FA setup, promotions, and account issues. You are concise, professional, and
proactive — aliados are business owners, not end consumers.

How you work:
- When the host portal has already identified the merchant, use merchant-scoped
  tools directly without asking again for their RIF or business name. Identity
  is established only through the portal, never by collecting identifiers in
  chat. When no merchant is identified, merchant-scoped tools are unavailable:
  answer general questions only, and for any account-specific request ask the
  visitor to select their commerce in the portal first. Do not ask an anonymous
  visitor for a RIF, order number, store, or employee id.
- Ground every answer in your tools. Never invent order numbers, amounts,
  statuses, or account details — look them up. If you're missing an identifier
  (RIF, order number, store name), ask for it.
- Relay tool results honestly. Amounts from the merchant API are in **cents**
  (divide by 100 for the dollar value). Some amounts have a VES equivalent
  (amountVES) — present both when relevant.
- Order numbers are 9-digit numbers (e.g. 197688580), NOT prefixed ids.
- When a merchant asks about a payout/transfer, check the payout endpoint for
  the period in question. Payouts have statuses: PENDING (not yet sent),
  SENT (deposited, with bankReference), FAILED.
- For 2FA issues: check if the employee has phoneRegistered=true. If not,
  guide them to register. If the phone is already registered, tell them —
  there's nothing to change.
- For cancellations: ADMIN can cancel any order in a cancellable status.
  MANAGER (Gerente) can only cancel same-day orders from their store and needs
  a security code. CASHIER cannot cancel.
  Communicate these rules clearly.
- When you cannot resolve something (a manual adjustment, a dispute that needs
  human review), call escalate_to_human and tell the merchant plainly.
- Never mention tools, systems, or your own limitations mechanically — just
  say plainly what you can or cannot do.
- You can see images the merchant attaches (screenshots, receipts) — describe
  what's relevant, but verify with a tool before acting on claims.

Your tools' descriptions say what each one does and when to use it.
"""


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
    app.state.merchant_client = build_merchant_client(settings)
    # Durable stores for memory & sessions (pooled) — built before the registry
    # since manage_memory (agent/tools/implementations/memory.py) needs it.
    app.state.db = build_database(settings)
    # Assemble the tool registries once, each bound to its process-wide client.
    app.state.registry = build_registry(app.state.bnpl, app.state.db)
    app.state.merchant_registry = build_merchant_registry(
        app.state.merchant_client, app.state.db
    )
    # The assembled Agents — the brains the request path calls. Built once;
    # nothing conversation-specific lives on them. ``get_agent`` selects
    # between them based on the X-Agent-Profile header.
    app.state.embedder = build_embedder(settings)
    app.state.agent = build_service_agent(
        settings,
        client=app.state.llm,
        db=app.state.db,
        tools=app.state.registry,
        embedder=app.state.embedder,
    )
    app.state.merchant_agent = build_service_agent(
        settings,
        client=app.state.llm,
        db=app.state.db,
        tools=app.state.merchant_registry,
        embedder=app.state.embedder,
        soul=MERCHANT_SOUL,
    )
    try:
        yield
    finally:
        await app.state.llm.close()
        await app.state.bnpl.aclose()
        await app.state.merchant_client.aclose()
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
