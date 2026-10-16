# ADR-0004 — Typed decisions: a decision model for the harness's judgment calls

- **Status:** Proposed (proof of concept on `feat/jev-harness`; nothing in production)
- **Date:** 2026-10-15
- **Deciders:** Alejandro León
- **Context service:** `agent-service` (Cashea Customer Support — aliados profile first)
- **Relates to:** extends **ADR-0001** (Agent = Model + Harness). Changes no storage decision in
  ADR-0002/0003. Replaces the implementation of the retrieval gate (ADR-0002, hero moment #1)
  and the skill trigger; adds the review hooks, the judge and the feedback loop.

---

## Context

`CLAUDE.md` §1 draws the line: *the model reasons; the harness guarantees*. Between those two
the harness itself has to **decide** small things on every turn, and until now it decided them
unevenly:

| Decision | Before this ADR |
| --- | --- |
| Does this message need the user's memory? | A Haiku call returning JSON we parse. Fails open on any parse error. No confidence. |
| Which skill policy applies? | Keyword overlap ≥ 2 between the message and the `SKILL.md` description. |
| Is the model's tool pick right? | Not decided. The model's word was final. |
| Should the model ask the user, or act? | Not decided. |
| Which retrieved rows belong in the prompt? | Not decided. Everything the stores returned went in. |
| Is this reply any good? | Judged offline on 7 eval cases. Never per turn. |
| Where did a thumbs-down come from? | Nobody looked. |
| Is a conversation worth distilling? Which facts? | A counter, then whatever the summarizer wrote. |

A free-text LLM call for a yes/no is the slow, expensive way to get an answer we then can't
threshold on. And the decisions that matter most for trust — calling the wrong tool, asking the
aliado something the agent could have looked up, shipping an ungrounded reply — weren't made by
the harness at all.

**Jev** (TypeSafe AI's "System One") is a decision model, not a language model: it takes a
`state` plus typed questions — `noul` (yes/no → P(yes)), `choice` (one of N labels →
distribution + confidence), `score` (a level on a rubric) — and returns typed answers with
calibrated probabilities in ~0.25 s. It never returns an invalid label and never returns prose to
parse.

## Decision

1. **A `Decider` seam, one facade, every site in one file.** `agent/decide/` holds the wire
   client (`jev.py`, plain `httpx`, no vendor SDK — same call as the Voyage embedder), the sites
   (`sites.py: Decisions`) and a scripted fake for tests and evals (`fake.py`). The harness
   depends on the `Decider` protocol and on `Decisions`, never on `JevClient`.

   | Site | Where it runs | Questions | What the harness does |
   | --- | --- | --- | --- |
   | `retrieval` | `Memory.gated_retrieve` | `needs_history` (noul), `memory_kind` (choice) | retrieve at P ≥ 0.5 from both stores; the kind is recorded (`would_narrow`), not acted on |
   | `memory_select` | after the stores return | one noul per row | keep rows at P ≥ 0.5 |
   | `skill_match` | `Memory.select_skills` | choice over the audience's skill descriptions + `none` | a confident pick loads that skill (or none); unsure → keyword matcher |
   | `tool_review` | `run_loop`, before a batch executes | `fits` (noul), `best_tool` (choice), `risk` (score) | a confident misfit gets a **suggestion as its tool result, once**; re-issued, it runs |
   | `ask_or_act` | `run_loop`, before `present_choice` suspends | choice `ask` / `act` | a confident `act` is handed back as the tool result, once; asked again, the question shows |
   | `consolidation_gate` | worker, before the summarizer | `worth_it` (noul) | below 0.3: mark consolidated, write nothing |
   | `fact_select` | worker, after the summarizer | one noul per candidate fact, with what is already stored | write only kept facts |
   | `judge` | end of every turn, after persistence | `quality` (score 0–4), `grounded`, `resolved` | scores on the message; an unsure `quality` escalates to the LLM judge |
   | `diagnose` | on a thumbs-down | `failure_site` (choice), `actionable` (noul) | a categorical score on the message |
   | `skill_proposal` | `propose_skill` tool (flag, off) | `recurring`, `duplicate`, `safe` (nouls) | traced for human review; never loaded, never written |

   Deterministic by design and **not** sites: `audience_of`, auth and the aliado's token, tool
   availability, and anything that moves money.

2. **Jev suggests; the chat model decides.** No site forces a `tool_choice`, rewrites a reply or
   routes to a sub-agent. The loop sites deliver a second opinion exactly once per tool (and once
   per turn for ask-or-act) as a tool result; if the model insists, the call runs. This keeps the
   harness *around* the loop and keeps ADR-0001's "no rigid classifier" intact.

3. **Confidence is thresholded; unsure is a valid outcome.** `DecisionConfig.confidence_threshold`
   (`JEV_CONFIDENCE_THRESHOLD`, default 0.8) gates every `choice`/`score` verdict; nouls are read
   at 0.5. Below the threshold a site takes its fallback — the behaviour it had before. The
   threshold is re-fit from the labelled set (`scripts/jev_replay.py`), never tuned by hand after
   an incident.

4. **Every site is total.** A failed call returns the pre-ADR behaviour with `source="fallback"`
   and a `decision` record carrying the error. No key configured → every site is a no-op, nothing
   is traced, and the harness runs byte for byte as before. The feature is additive and removable.

5. **No shadow mode, no per-site switches.** This is a proof of concept with no production
   traffic: Jev is on wherever a key is configured, and the impact is measured — not staged.

6. **Measurement is built in, Langfuse-ready.** The tracer gains two first-class records:
   `decision` (site, source, the raw Jev primitives, the derived verdict, whether the harness
   acted, and — where the previous method is cheap enough to still run — its verdict and the
   agreement) and `score` (Langfuse's score shape: `name`, `value`, `data_type`, `comment`,
   keyed by the assistant `message_id`). Both also land in `decisions.jsonl` / `scores.jsonl`
   and as OpenInference `GUARDRAIL` / `RERANKER` / `EVALUATOR` spans. The user's thumbs become a
   `user_feedback` score on the same key, so judge, diagnosis and feedback join without a schema.
   Wiring Langfuse later is a sink, not a redesign.

7. **Hard budgets per turn, as CLAUDE.md §2.3 asks.** `max_tool_calls` and `max_turn_tokens`
   sit next to `max_iterations`. Exceeding one ends the turn with the same limit reply and a
   traced reason. For aliados there is no escalation path yet (`fdf2474`), so the reply is the
   existing one; the reason is in the trace and on the message's meta.

## Consequences

- **Latency.** ~0.25 s per decision (p50 255–290 ms on the labelled set). The retrieval gate
  gets *faster* (it replaces a Haiku round-trip) and runs concurrently with the skill match.
  A tool batch adds one concurrent review round-trip; the judge adds ~0.3 s *after* the reply
  is persisted — the user already has their answer, the HTTP response closes slightly later.
- **Cost.** ~400–800 input tokens per decision; a typical merchant turn makes 2–4 calls. Under
  one Haiku gate call in cost at Jev's pricing.
- **Data leaves the process.** The `state` is the user's message, a text-only truncated window
  of the conversation (tool arguments included, tool outputs cut at 600 chars, images reduced to
  a marker), the retrieved rows, and — for the judge — the reply. Never the full history, never
  image bytes, never the aliado's token. Same trust class as the LLM provider. See
  `docs/SECURITY.md` §4.
- **Search query.** With the decision model the memory search runs on the message itself (Jev
  writes no text); the stores already do FTS + embeddings over it (ADR-0003) and the per-row
  re-rank recovers precision. Both stores are always searched: the first design narrowed to
  one store on a confident `memory_kind`, and the live smoke showed a confident "episodes"
  skipping the facts that held the answer. One extra Postgres query is cheaper than that
  miss; the trace keeps `would_narrow` so the disagreement rate can be measured.
- **State size.** A free-text `state` is capped at `max_state_chars` (48k) from the tail. Jev
  rejects ~32k tokens with `400 max_tokens_exceeded`; the consolidation gate hit it on a user
  with a long unconsolidated backlog (fallback: proceed), hence the cap.
- **Recall depends on embeddings.** Facts written while the embedder was unavailable (Voyage
  `429` during a consolidation sweep) have no vector and the semantic search excludes them;
  the summarizer writes English while the FTS dictionary is Spanish, so keyword search does
  not rescue them either. Pre-existing (ADR-0003), surfaced by the smoke; a backfill job for
  `embedding IS NULL` rows is the fix, outside this ADR.
- **Streaming.** The judge scores after the fact, so streaming is unaffected. A *reply gate*
  (hold a draft back) was deliberately not built: it can't hold a streamed reply.
- **Testability.** `FakeDecider` scripts answers per call; every site and both loop hooks have
  Level-1 tests; the labelled set (`evals/jev/cases.jsonl`, 94 cases in aliado language) is the
  Level-2 eval, run by CI when a key is available.

## Alternatives considered

- **Keep asking Claude (Haiku) for each decision as JSON.** Rejected: slower, costlier, no
  calibrated confidence to route on, and a parse-failure mode on every call.
- **Jev as a pre-router that picks the tool before the model runs (forced `tool_choice`).**
  Rejected: the rigid-classifier anti-pattern ADR-0001 exists to avoid. Kept as a *review*
  the model can overrule.
- **Shadow mode with per-site `off | shadow | on` switches.** Rejected for the proof of concept:
  no traffic to shadow against; it would only delay measurement. The replay against the
  labelled set is the gate instead.
- **Deterministic `Tool.risk` flags instead of a scored risk.** Not exclusive with this ADR;
  deferred. Every merchant tool is read-only today, so the `risk` answer is recorded but never
  acted on.
- **Sub-agents chosen by Jev (`delegate_task`).** Out of scope now; the data from `tool_review`
  and `ask_or_act` will say whether delegation is ever needed.
- **The official `typesafe-sdk`.** Rejected: one more dependency for a ~100-line wire contract
  we can own and test with `MockTransport`.

## Open

- **Agent-authored skills (B).** `propose_skill` only traces. Storing approved proposals needs
  a Postgres table (`skill_proposals`) with a review queue and a loader that reads approved rows
  — its own ADR. Until then the `skill_proposal` trace event is the inbox.
- **Contact drivers.** `config/contact_drivers_aliados.yaml` describes a `contact_driver` site
  (classify the opener into a CD, tag Intercom, load its skill). Rescued as reference; not a
  site yet — the skills it maps to don't exist in this tree.
- **Threshold re-fit.** 0.8 came from the first probe and held on the labelled set (wrong
  answers' confidence median 0.18–0.81 vs right 0.74–1.0, per site). Revisit with real traffic.
  First live smoke (26 consumer turns): the `judge`'s `quality` sat below 0.8 on 17 of 23
  turns, so the LLM judge ran on 74 % of them — the accept/escalate split saves little at this
  threshold for that one site, and the labelled set's right-answer median for `judge` is 0.74.
  A per-site threshold for `judge` (≈0.6) is the obvious candidate; decide from the replay.
- **`resolved` is too lenient.** Jev answered `resolved=true` on every live turn, including
  replies that only asked the customer for an order number; the LLM judge said `false` on
  those. The noul's criteria need a sharper `false` ("the reply asks for information or
  defers") before `jev.resolved` can be trusted as a metric.
- **`ask_or_act` only sees `present_choice`.** In the smoke the model never called it: when it
  wanted to ask, it asked in prose. The site is correct but rarely reached; reviewing a
  text reply that ends in a question would be a reply gate, which streaming rules out (above).

## Reversal

Delete `agent/decide/`, remove the `decisions=` / budget arguments from `build_agent`, `Memory`,
`run_loop` and the consolidation functions, the `score` method on the tracer, and the eight
`Settings` fields. The Haiku gate, the keyword matcher and the unreviewed loop are still in the
tree as the fallbacks; nothing else changes.

## References

- `src/agent/decide/{jev,sites,fake}.py` · `src/agent/loop/agent.py` (review hooks, budgets) ·
  `src/agent/memory/__init__.py` (gate, re-rank, skills) · `src/agent/memory/consolidation.py` ·
  `src/agent/app.py` (judge, feedback) · `src/agent/ops/tracing.py` (decision / score records).
- `evals/jev/cases.jsonl` · `scripts/jev_replay.py` · `scripts/jev_report.py` ·
  `docs/jev-runbook.md`.
- TypeSafe AI, System One API: `POST https://api.typesafe.ai/v1/systemone`.
- "JEV-as-a-Judge: Accept When Confident, Escalate When Unsure" (arXiv 2609.26550) — the
  accept/escalate pattern; confidence is an escalation signal, not a certificate.
