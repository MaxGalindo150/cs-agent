# Security notes — agent-service

Known limitations that are accepted for now, with an explicit condition for
when they must be fixed. Not an ADR (no alternatives to weigh) — a running
list of security debt, kept next to the code it describes.

---

## 1. Identity: verified for the widget, self-asserted only in dev

**Resolved for the embedded widget.** `service/core/identity.py::get_principal`
now verifies an `Authorization: Bearer` session token, issued by
`POST /v1/auth/session` only after the host app's Firebase ID token checks out
(`service/core/host_token.py`: Google signature, `aud`/`iss` = the configured
project, expiry, `auth_time`). An invalid or expired bearer is a 401, never an
anonymous fallback. Both `FIREBASE_PROJECT_ID` and `SESSION_SIGNING_KEY`
default to empty, which issues and accepts nothing (fail closed).

**Still accepted (dev-only):** with no bearer, `X-User-Id` / `X-User-Email` are
trusted verbatim when `settings.is_development` — the demo page's simulated
login. Anyone can impersonate anyone there; outside dev these headers are
ignored.

**Residual risks:**

- A session token is a bearer credential for its TTL (`SESSION_TTL_SECONDS`,
  15 min by default): leaked, it can be replayed until it expires. Not
  revocable — keep the TTL short rather than adding a denylist.
- `SESSION_SIGNING_KEY` signs every session; rotating it logs every widget
  out (they renew transparently through the host's `getToken`).
- Firebase revocation (`revoked` users, disabled accounts) is not checked —
  only signature and expiry, so a revoked host token stays usable for the rest
  of its hour. Acceptable while the session TTL is short; revisit if
  revocation must take effect immediately.

---

## 2. Session ownership — resolved

Resuming a conversation (`/v1/chat`, `/v1/chat/stream` with a `session_id`),
reading its messages and deleting it all go through
`service/core/session_access.py`: the caller's `user_id` must equal the one
stamped on the session at creation (`NULL` for anonymous). A mismatch is a 404,
indistinguishable from a missing session. `GET /v1/sessions` lists only the
caller's own sessions, and nothing for an anonymous caller.

**Remaining:** anonymous sessions are reachable by anyone holding their
(unguessable, UUIDv4) id — that id is the only credential an anonymous visitor
has.

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

- `src/service/core/identity.py` — identity resolution (bearer, then dev headers).
- `src/service/core/host_token.py` / `session_token.py` — Firebase verification and
  the widget session token.
- `src/service/core/session_access.py` — session ownership.
- `src/agent/memory/models.py` — `ChatSession.user_id`, `Fact.user_id`,
  `Episode.user_id`.
- `src/agent/tools/registry.py` — `Tool.requires_identity` gate (the pattern
  item 3's future write path must reuse).
- `docs/ADR/0002-memory-and-session-persistence.md` — session persistence.
