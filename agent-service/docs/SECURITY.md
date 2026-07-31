# Security notes — agent-service

Known limitations that are accepted for now, with an explicit condition for
when they must be fixed. Not an ADR (no alternatives to weigh) — a running
list of security debt, kept next to the code it describes.

---

## 1. Identity is self-asserted, not verified (dev-only)

**What:** `service/core/identity.py::get_principal` trusts the `X-User-Id` /
`X-User-Email` headers verbatim — no signature, no token, no verification.
It only runs when `settings.is_development` is true; everywhere else it
returns `None` (and `Settings.environment` defaults to `"prod"`, so a
deployment that omits `ENVIRONMENT` fails closed, not open).

**Risk:** inside a `dev` environment, any caller can attribute a request —
and now a persisted `chat_sessions.user_id` row (ADR-0002) — to *any* user id
just by setting the header. Impersonation is trivial in dev.

**Blast radius today:** bounded. Nothing currently *reads* `user_id` to
authorize access — it is write-only attribution data (which conversation
"belongs" to whom, or which fact/episode is about whom — `facts.user_id` /
`episodes.user_id`), not yet an access-control gate. It graduates from
"corrupted ownership data" to "real access-control bypass" the moment
something scopes a *read* by trusting this value — e.g. a "list my
sessions" endpoint, or semantic-memory retrieval filtered by `user_id`.

**Accepted because:** this is an explicit, temporary stub (see the
docstring in `service/core/identity.py`), built to simulate per-user
identity end-to-end (the demo login selector in the frontend) before real
auth exists anywhere in the stack.

**Fix:** replace `get_principal`'s body with real verification (extract the
subject claim from a verified bearer token instead of trusting a header).
Its shape (`-> Principal | None`) does not change, so no caller — `agent/`,
`chat.py`, `chat_stream.py` — needs to change when this happens.

**Until then:** do not build authorization (session-ownership checks,
per-user data filtering) on the assumption that `Principal`/`user_id` is a
verified identity. See item 2.

---

## 2. Session-ownership is not verified on resume

**What:** resuming a conversation by `session_id` (`POST /v1/chat` /
`/v1/chat/stream` with an existing `session_id`) does not check that the
caller's resolved `Principal` matches the session's stored `user_id`.

**Risk:** low today — `session_id` is an unguessable UUID, and nothing
scoped to a specific user is exposed through a resumed session beyond its
own messages.

**Fix:** once item 1 lands (real auth), add an ownership check in the chat
endpoints: reject (or silently start a fresh session) when
`principal.user_id != session.user_id`.

---

## 3. Facts and episodes must never be creatable without an identified user

**What:** every `Fact` and `Episode` row is inherently personal (a fact
*about* someone, an episode of something that happened *to* someone) — there
is no "global"/shared-memory use case in this domain. `facts.user_id` /
`episodes.user_id` exist (nullable, for migration convenience) ahead of any
write path — nothing creates facts or episodes yet (no `remember` tool, no
consolidation worker; see `agent/memory/__init__.py`).

**Rule:** when that write path is built (a memory-management tool ported
from `waku-agent`'s `manage_memory`, and/or a consolidation worker), it must
require a resolved `Principal` and refuse to write when there is none —
mirroring the `requires_identity` gate already enforced for tools in
`agent/tools/registry.py::ToolRegistry.execute`. An anonymous visitor's
"I'm Max" is fine as *session-local* context (it already lives in
`chat_messages` for that conversation) — it must never become a durable,
cross-session fact with no owner.

**Read side:** retrieval (`Memory.gated_retrieve` → `facts.search` /
`episodes.search`) must filter by the caller's `user_id` — never return, nor
search across, another user's facts/episodes.

---

## Referenced from

- `src/service/core/identity.py` — the stub itself.
- `src/agent/memory/models.py` — `ChatSession.user_id`, `Fact.user_id`,
  `Episode.user_id`.
- `src/agent/tools/registry.py` — `Tool.requires_identity` gate (the pattern
  item 3's future write path must reuse).
- `docs/ADR/0002-memory-and-session-persistence.md` — session persistence.
