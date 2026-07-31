# ADR-0001 — Agent architecture: single agent + deterministic tools + on-demand skills over a hand-rolled harness

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Maximiliano Galindo
- **Context service:** `agent-service` (EigenCore Customer Support)

---

## Context

We are building a Customer Support agent (Python/FastAPI, Cloud Run). The first flow is
payment validation from a receipt image. We need to choose the runtime shape *before*
writing feature code, because it dictates everything downstream: how tools are called,
where business logic lives, how we test, and how we control cost and risk.

Two forces shape this decision:

1. **v1 taught us where naive agent designs fail.** The prior platform used a rigid input
   classifier that routed each message to an isolated sub-agent (internally "the Cheo bug").
   That design mis-routed requests, lost cross-turn context, and was hard to evaluate. It also
   pushed business judgments into the LLM ("is this payment valid?"), which is neither testable
   nor auditable. See `../../../docs/v1-lessons.md`.
2. **Agent frameworks are a liability at our scale.** The loop we need — steps, tools, streaming,
   retries, budgets — is a few hundred lines we can fully control, test, and delete. A heavy
   orchestration framework buys hidden control flow and version churn we don't want.

The governing principle is **`Agent = Model + Harness`**: the model reasons, the harness
guarantees. We want guarantees (schema validation, permissions, budgets, tracing) in
deterministic code, and reasoning in the model — with a clean seam between them.

## Decision

Adopt a **single agent + deterministic tools + on-demand skills**, driven by a
**hand-rolled harness (~200 lines)** over the provider SDK. No agent framework.

Concretely:

1. **The LLM never executes side effects.** It only emits structured tool calls. The harness
   is the sole executor and enforces, in order: **schema validation (pydantic) → permission /
   risk check → budget check → execute with timeout → inject result → continue the loop.**
2. **Business decisions are deterministic code.** Approving a payment, issuing a refund, and
   similar are pure, testable functions (`tools/**/rules.py`) — never a free-text LLM verdict.
3. **One agent, implicit routing.** No upfront classifier and no isolated sub-agents. The
   single agent decides turn by turn with full context and the available tools.
4. **Skills load on demand (progressive disclosure).** The context carries a *skill index*
   (name + when-to-apply) always, but a skill's full policy text loads only on the turn it
   applies. Skills are short (≤60 human-written lines).
5. **Hard budgets per conversation** (turns, tool calls, tokens). Exceeding a budget produces
   `needs_human` — a first-class escalation result — never a silent truncation.
6. **Everything is traceable** to Langfuse under a conversation-bound trace ID: one trace per
   conversation, one span per turn, child spans per tool call and skill load.
7. **Context is ordered stable-first for prompt caching:** system prompt → tool schemas →
   skill index → active skills → (compacted) history → new message.

## Consequences

**Positive**
- Business logic is unit-testable without the LLM; correctness does not depend on prompt luck.
- Auditable: every side effect passes through one choke point (the harness) and is traced.
- Cost-controlled by construction (budgets) and cheaper via prompt caching (stable-first order).
- No framework lock-in or version churn; the loop is ours to change and delete.
- Avoids the v1 mis-routing and context-loss failure modes.
- **Stateless by construction:** the loop holds no cross-request state, so it fits serverless
  (Cloud Run) directly. Tenancy is out of scope here — the platform is single-tenant first
  (see `CLAUDE.md` §9).

**Negative / costs**
- We own and maintain the loop, retries, compaction, and permission matrix ourselves.
- A single agent with many tools needs a **tool-selection eval** to guard against wrong-tool
  choices (mitigation: deploy-blocking threshold, per the testing strategy in `CLAUDE.md` §8).
- Progressive-disclosure skill loading adds context-assembly logic that must itself be tested.

## Alternatives considered

- **Rigid classifier → isolated sub-agents (v1 shape).** Rejected: mis-routing, lost context,
  untestable business judgments. This is the failure we are explicitly designing away from.
- **Heavy agent framework (LangGraph / CrewAI / etc.).** Rejected: version churn, hidden control
  flow, and weight far exceeding a ~200-line loop we can own and test.
- **Let the LLM make the business decision directly.** Rejected: not testable, not auditable,
  not safe for money-moving actions.

## Reversal

The harness is intentionally rippable. If a future need (e.g. graph-based multi-agent
orchestration) justifies a framework, replace the loop behind the same tool/skill interfaces
and supersede this ADR. Business rules in `tools/**/rules.py` stay valid regardless of the
runtime around them.

## References

- `CLAUDE.md` (this service) — principles §2, layout §4, testing §8, anti-patterns §10.
- `../../../docs/*` — parent-monorepo docs from the retired Go platform; historical, being realigned.
