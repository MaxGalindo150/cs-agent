"""Who may read or continue a conversation (docs/SECURITY.md §2).

A session belongs to whoever started it: the ``user_id`` stamped at creation,
or nobody (``NULL``) for an anonymous visitor. A caller reaches it only with
the same identity — a signed-in user can't open an anonymous session or
someone else's, and an anonymous caller can't open a signed-in one. A
mismatch looks exactly like a missing session (404), so ids can't be probed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from agent.identity import Principal
from agent.memory.db import Database
from agent.memory.repositories import SessionRepository


class SessionAccess:
    def __init__(self, get_db: Callable[[], Database]) -> None:
        # A getter, not the pool: the pool is read only when there is a
        # session to check, so routes that never receive a session_id don't
        # need one (and their contract tests run without a database).
        self._get_db = get_db

    async def require(self, session_id: uuid.UUID, principal: Principal | None) -> None:
        async with self._get_db().session() as session:
            chat_session = await SessionRepository(session).get_session(session_id)
        caller = principal.user_id if principal else None
        if chat_session is None or chat_session.user_id != caller:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")


def get_session_access(request: Request) -> SessionAccess:
    """Dependency for the chat routes (see service/core/agent.py::get_database
    for the pool itself)."""
    return SessionAccess(lambda: request.app.state.db)
