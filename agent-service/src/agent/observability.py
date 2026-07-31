"""The observer seam — one definition of the cross-cutting ``notify`` callback.

An observer receives ``(event_name, payload)`` and lets a gateway stream tool
calls live, or lets ops/tracing record them, without either being wired into
the code that emits the events. It is threaded through several layers — the
harness loop, the memory facade's ``gated_retrieve``, the runtime session — so
its type lives here, defined once and imported, rather than re-declared per
module.

**Divergence from Waku, taken deliberately.** Waku keeps these inline in
``loop/agent.py`` and imports them from there where needed (``app.py``). We lift
them to a shared module because ``mypy --strict`` (which Waku does not run)
requires ``notify`` to be typed at every call site, and the callback is threaded
through more layers here — importing from ``loop`` would make storage depend on
the orchestrator. Same shape as Waku's ``Observer`` / ``LoopEvent``; only the
home moved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# An event payload: an open dict keyed by the emitter (e.g. {"delta": "..."},
# {"decision": "retrieve", "reason": "..."}). Intentionally loose — observers
# render or record it, they do not depend on a fixed schema.
LoopEvent = dict[str, Any]

# The callback itself: (event_name, payload) -> None.
Observer = Callable[[str, LoopEvent], None]
