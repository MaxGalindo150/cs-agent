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
"belongs" to whom), not yet an access-control gate. It graduates from
"corrupted ownership data" to "real access-control bypass" the moment
something scopes a *read* by trusting this value — e.g. a "list my
sessions" endpoint, or the planned `facts.user_id` semantic-memory scoping.

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

## Referenced from

- `src/service/core/identity.py` — the stub itself.
- `src/agent/memory/models.py` — `ChatSession.user_id`.
- `docs/ADR/0002-memory-and-session-persistence.md` — session persistence.
