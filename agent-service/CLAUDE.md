# CLAUDE.md — Agent Service (EigenCore Customer Support)

> Operating contract for anyone (human or agent) working in this repo.
> Read this before writing code. It overrides general habits where it conflicts.

---

## 1. What this service is

A **Customer Support agent** microservice for EigenCore.

- **Language / runtime:** Python 3.13, FastAPI (async), served by uvicorn.
- **Package manager:** `uv`.
- **LLM (reasoning):** Anthropic **Claude** via the official `anthropic` SDK. Model IDs live in config, never hardcoded (`ANTHROPIC_CHAT_MODEL`, `ANTHROPIC_FAST_MODEL`, `ANTHROPIC_CHAT_FALLBACK_MODEL`).
- **OCR (perception):** **Mistral OCR** (Document AI mode) — used *only* to extract text/fields from images. It does not make decisions.
- **Observability:** Langfuse (traces) + structlog (structured logs).
- **Deploy target:** GCP **Cloud Run** — **serverless-oriented from the start** (stateless request handling; no state held in the process). We develop locally (with Docker) and grow toward the cloud gradually; the code stays deploy-ready without depending on cloud infra to run or test.
- **Shape:** a two-package layout — `agent/` (the provider-neutral brain: loop, tools, later memory/skills) and `service/` (the FastAPI transport). A prior Go implementation was retired; **this Python service is the platform now**, built up gradually.

**Guiding principle — `Agent = Model + Harness`.** The model *reasons*; the harness *guarantees*. Every business decision (approve a payment, issue a refund) is deterministic, testable code — never a free-text LLM judgment.

First business flow (not yet built): **payment validation from a receipt image** using Mistral OCR + deterministic rules.

---

## 2. Non-negotiable principles

These are the spine of the design. Do not violate them without an ADR that supersedes ADR-0001.

1. **The LLM never executes anything directly.** It returns structured tool calls. The harness: validates schema (pydantic) → checks permissions/risk → checks budget → executes with a timeout → injects the result back. Business logic lives in deterministic code.
2. **One agent, many tools, skills on demand.** No rigid input classifier routing to isolated sub-agents (that was v1's "Cheo bug"). Routing is implicit, turn by turn, with full context. Skills load a domain's *policy* only when it applies (progressive disclosure).
3. **Hard budgets per conversation.** Max turns, tool calls, and tokens. Exceeding a budget escalates to a human — it never silently truncates.
4. **Everything is traceable.** Every tool call, decision, and skill load lands in Langfuse under a trace ID bound to the conversation.
5. **Rippable harness.** No heavy agent framework. The loop is ~200 lines of our own code over the provider SDK. If we can't delete it in an afternoon, it's too clever.
6. **Escalation is a first-class result**, not an error. `needs_human` has its own flow.

---

## 3. Hard-won lessons we honor here

Paid for by a prior platform. They hold regardless of stack — keep them.

- **Never hold a DB connection while awaiting the LLM.** The old runtime exhausted its pool this way (2,651 HTTP 500s in one day; LLM calls take 6–30s). Every DB read/write is a short, per-statement pool call. No transaction spans a provider call.
- **Idempotency from day one.** Dedup by reference + image hash with a unique constraint. Assume every inbound message can be delivered twice.
- **Dead-letter, never HTTP 200 to hide a failure.** Dropping messages by acking errors is how the old platform lost data. Failures must be visible and retryable.
- **Keep the core business-domain-agnostic and config-driven.** No client-specific logic baked into code paths. (Multi-tenancy itself is a *later* phase — see §9; don't add `tenant_id`/RLS yet.)
- **Secrets in Secret Manager**, never in the service YAML or committed env files. Locally: `.env` (git-ignored).
- **No orchestration framework.** A heavy framework buys hidden control flow and version churn — our own ~200-line loop instead.

---

## 4. Repository layout

Two packages under `src/`, split by responsibility. The dependency arrow points **one way**:
`service/` (and a future `worker/`) → `agent/`. The brain never imports the transport — so it
stays testable in isolation and reusable across entrypoints.

Built today ✅; planned ⛔ (not built — do not assume it exists).

```
agent-service/
├── pyproject.toml              ✅ uv, ruff, mypy (strict), pytest-asyncio
├── .python-version             ✅ 3.13
├── Dockerfile                  ⛔ multi-stage, slim, non-root  (planned)
├── Makefile                    ⛔ dev / test / lint / types / eval  (planned)
├── src/
│   ├── agent/                  ·· the brain: provider-neutral, no HTTP/FastAPI imports
│   │   ├── loop/agent.py       ✅ run_loop (async): reason → act → observe → repeat
│   │   ├── tools/registry.py   ✅ Tool + ToolRegistry (async execute; returns plain dicts)
│   │   ├── memory/             ⛔ semantic / episodic / procedural over Postgres  (later)
│   │   ├── skills/             ⛔ loader.py + on-demand SKILL.md policies  (later)
│   │   └── runtime/            ⛔ session.py — working-memory assembly per turn  (later)
│   └── service/                ·· FastAPI transport + wiring (imports agent, never reverse)
│       ├── main.py             ✅ app factory + lifespan
│       ├── core/config.py      ✅ pydantic-settings, env-driven
│       ├── api/health.py       ✅ liveness probe
│       └── worker/             ⛔ async consumer (e.g. memory consolidation)  (later)
├── tests/                      ✅ contract (health);  ⛔ unit / integration
├── evals/                      ⛔ L1 deterministic / L2 component / L3 trajectory
└── docs/
    ├── ADR/                    ✅ ADR-0001 (agent architecture)
    └── runbook.md              ⛔ 3am playbook  (planned)
```

> Imports use the top-level package names `agent.*` and `service.*` (src-layout; no `src.` prefix).
> The tool registry is **provider-neutral** — it returns plain dicts; the loop adapts them to the
> Anthropic SDK's types only at the boundary (`cast` in `agent/loop/agent.py`).

**The harness loop, in words** (target design — the core loop in `agent/loop/agent.py` is built,
the rest is planned):
`receive message → load session (history + state) → build context (stable-first for prompt caching: system prompt → tool schemas → skill index → active skills → compacted history → new message) → call LLM → if tool call: validate schema → check risk → check budget → execute with timeout → inject result → loop; if text: reply → persist session + full trace.`

---

## 5. Working style (how I want you to operate)

Inherits the global config in `~/.claude/CLAUDE.md`. In this repo specifically:

### Engineering bar (non-negotiable)

Act as a top-tier software / AI engineer, and **always follow industry best practices** — no shortcuts, no "quick and dirty". **Every line of code is weighed against four axes — efficiency, security, scalability, and modularity — and the reasoning is made explicit.** Concretely, before writing or accepting code, ask:

- **Efficiency:** Is this the cheapest correct path? No needless I/O, allocations, or blocking calls on the hot path. Async for all external I/O. Prompt caching and budgets respected. Don't pay for work you don't need.
- **Security:** What is the trust boundary here? Validate all input at the edge (pydantic). Never leak secrets, internal config, stack traces, or PII in responses/logs. Least privilege. Treat every inbound message and every model output as untrusted. Money-moving actions are deterministic and audited.
- **Scalability:** Does this hold under Cloud Run autoscaling and concurrency? No shared mutable process state assumed. **No DB connection held across an LLM call.** Idempotent by design. Backpressure over unbounded work. Stateless request handling; state lives in the session store.
- **Modularity:** Is each piece small, single-responsibility, and replaceable? Clear seams and stable interfaces between layers (harness ↔ tools ↔ skills ↔ LLM client ↔ storage). Depend on abstractions, not concretions, so any part (LLM provider, session store, OCR engine) can be swapped or deleted without a rewrite. Code that is easy to delete over code that is merely easy to extend.

If a change trades one axis for another, say so and let me decide. "It works" is not the bar — it must be efficient, safe, scalable, and modular.

### Collaboration

- **Low autonomy, collaborative, step by step.** Do not do large changes in one shot. Confirm the goal and outline a plan before non-trivial work; wait for approval.
- **Explain decisions.** This project is also a teaching context — narrate *why*, name tradeoffs and risks, say when you're uncertain.
- **Ask before, never assume:** schema/migration changes, deleting or renaming files, new dependencies, anything touching auth/security, config/env changes, pushing to `main`.
- **Local-first.** Everything must run and be testable locally (Docker included). Do not introduce a hard dependency on cloud services to develop or run tests.
- Respond in the language I use (Spanish or English). Be concise; skip filler.

---

## 6. Conventions

- **Style:** `ruff` (line length 88, rules `E,F,I,UP`). Type hints everywhere; `mypy --strict` must pass (pydantic plugin on).
- **Validation:** `pydantic` / `pydantic-settings` at every boundary (API in, tool calls, config). Structured outputs over free-text parsing.
- **Async:** all external I/O (`anthropic`, Mistral, DB, HTTP) is async (`httpx` async). Use `context`/timeouts for cancellation.
- **SDK at the boundary only:** keep provider types out of the core. The registry returns plain dicts; the loop narrows blocks with `isinstance` and `cast`s to the Anthropic types only at the adapter seam (`agent/loop`).
- **Errors:** explicit, no silent failures. No bare `except`.
- **Prompts are code:** version them, keep prompt logic separate from business logic. Skills are ≤60 human-written lines — never 300-line LLM-generated files.
- **Logging:** structlog, structured. Log LLM inputs/outputs for debugging with **PII scrubbing**.
- **Commits:** Conventional Commits (`type(scope): description`). Small, focused. Review the diff before committing; ask me to review too. Never force-push `main`.

---

## 7. Commands

> Some tooling is planned (§4). Use `uv` directly until the Makefile lands.

```bash
uv sync --extra dev            # install (incl. dev tools)
uv run uvicorn service.main:app --reload   # run API locally
uv run ruff check src tests    # lint
uv run ruff format src tests   # format
uv run mypy src tests          # type-check (strict)
uv run pytest                  # tests (asyncio_mode=auto, testpaths=tests)
```

---

## 8. Testing & evals (three levels)

Testing strategy is part of the "robust base" — not an afterthought. **Rule of gold: every production bug becomes an eval case before it is fixed.**

- **Level 1 — deterministic tests** (pytest, CI, <30s): business rules with edge cases, pure harness logic (budget, compaction), contract tests that tool-call schemas don't break. No network.
- **Level 2 — component evals** (against the real LLM, pre-deploy): tool-selection eval (did the agent pick the right tool? — the Cheo lesson, block deploy under a data-defined threshold), extraction eval (anonymized receipts + ground truth, exact match per field), skill-adherence eval (LLM-as-judge on policy).
- **Level 3 — trajectory evals** (weekly + pre-major-release): full simulated conversations, adversarial (prompt injection, fake images).

Target: 80%+ coverage on business logic.

---

## 9. Current state & open decisions

**Do not implement past this line without confirming with me.** We make the base robust first and grow the platform gradually.

**Built and green:** the `agent/` ↔ `service/` package split; the async `run_loop` (`agent/loop/agent.py`) and provider-neutral `ToolRegistry` (`agent/tools/registry.py`); `/healthz` with contract tests. `ruff`, `mypy --strict`, and `pytest` all pass locally.

**Near-term direction — serverless-ready, single-tenant:**
- **Single-tenant first.** Multi-tenancy is a deliberate *later* phase — **do not add `tenant_id` columns, RLS, or an org/workspace hierarchy yet.** Design the core so it *can* grow into it; don't build it now.
- **State backend → PostgreSQL (target, not built).** Memory and sessions will live in Postgres so the request path stays stateless under Cloud Run. **Do not write migrations or ORM models** until it has its own ADR.
- **Keep the request path stateless** — no shared mutable process state, nothing assuming a single long-lived instance.

**Later phases (not now):** `agent/memory` (Postgres), `agent/skills`, `agent/runtime` (sessions), `service/worker` (async consolidation), Langfuse tracing wiring, Dockerfile + Makefile, and the payment-validation business flow. `README.md` still to be written.

---

## 10. Anti-patterns (already-paid lessons — do not repeat)

- ❌ Rigid input classifier → isolated sub-agents (the Cheo bug).
- ❌ Asking the LLM "is this payment valid?" — validation is code.
- ❌ A heavy agent framework for a 200-line loop we should own.
- ❌ LLM-generated 300-line `SKILL.md` files — 30–60 human lines, only where the agent actually errs.
- ❌ Evals "when there's time" — the dataset is built with the feature, not after the first incident.
- ❌ Manual deploys — the pipeline exists from Phase 0 or it never will.
- ❌ Holding a DB connection across an LLM call.

---

## 11. Pointers

- Architecture decisions: `docs/ADR/` (start at `0001-agent-architecture-harness.md`).
- Security notes (known limitations, accepted risks, their fix conditions): `docs/SECURITY.md`.
- Runbook (3am): `docs/runbook.md` (planned).
- Parent monorepo docs (`../docs/*`) describe the retired Go platform and are being realigned — treat them as historical until updated.
