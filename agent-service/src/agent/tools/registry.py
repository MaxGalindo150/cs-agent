"""Tool registry — the 'Agentic Tools' box on the whiteboard.

A tool is three things: a name+description the model reads, a JSON schema for
its arguments, and a Python function that runs. That's it. (Registry pattern
adapted from launch-agentic-rag's app/agents/tools/registry.py.)
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agent.tools.context import ToolContext

# `{arg}` placeholders in a progress_label. Deliberately not str.format: that
# would expose format specs and attribute access (`{a.__class__}`) to a template
# interpolated with model-supplied arguments, and would raise KeyError the first
# time the model omitted an optional one. A plain substitution can do neither.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Fallback labels, derived from a tool's `verb_noun` name when it declares no
# progress_label. Means a new tool always renders something sensible.
_VERBS = {
    "get": "Getting",
    "fetch": "Fetching",
    "list": "Listing",
    "search": "Searching",
    "find": "Searching",
    "check": "Checking",
    "create": "Creating",
    "add": "Adding",
    "set": "Updating",
    "update": "Updating",
    "cancel": "Cancelling",
    "delete": "Deleting",
    "send": "Sending",
}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Awaitable[str]]  # tools return a string the model observes

    progress_label: str | None = None
    """What a UI shows while this runs, e.g. ``"Getting order {order_id}"``.

    ``{arg}`` placeholders are filled from the call's arguments; an argument the
    model did not supply collapses to nothing. Optional — a tool that declares
    none gets one derived from its name. It lives here, next to `description`,
    so the tool is the single source of truth for how it presents itself and a
    rename can never leave a client showing a stale label.
    """

    requires_identity: bool = False
    """If true, ``ToolRegistry.execute`` refuses to run this tool unless the
    call carries a ``ToolContext`` with a resolved ``Principal`` — and calls
    ``fn(ctx=ctx, **args)`` instead of ``fn(**args)``. Never exposed in
    ``to_api()``: the model never sees this flag, only its effect."""

    needs_context: bool = False
    """Like ``requires_identity``, but without the identity requirement: the
    tool still receives ``fn(ctx=ctx, **args)``, for something else on
    ``ToolContext`` (e.g. ``session_id``) that an anonymous caller can also
    have. Set this instead of ``requires_identity`` when a tool needs context
    but must keep working for a caller with no resolved ``Principal``."""

    def to_api(self) -> dict[str, Any]:
        """The shape the Messages API expects in its `tools=` parameter."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def label(self, args: dict[str, Any]) -> str:
        """This call, in words: ``get_order {order_id: "ord_1"}`` -> "Getting
        order ord_1". Never raises and never returns empty."""
        if self.progress_label:
            filled = _PLACEHOLDER.sub(
                lambda m: str(args.get(m.group(1), "")), self.progress_label
            )
            # Collapse the gap a missing argument leaves behind.
            cleaned = " ".join(filled.split())
            if cleaned:
                return cleaned
        return _derive_label(self.name)


def _derive_label(name: str) -> str:
    """ "get_order" -> "Getting order". Falls back to the name spelled out, so an
    unrecognised shape shows something honest instead of an invented verb."""
    head, _, rest = name.partition("_")
    verb = _VERBS.get(head)
    if verb and rest:
        return f"{verb} {rest.replace('_', ' ')}"
    return name.replace("_", " ")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self, ctx: ToolContext | None = None) -> list[dict[str, Any]]:
        """The tools the model may call this turn — never the ones it
        structurally can't use.

        A tool with ``requires_identity=True`` is omitted entirely when there
        is no resolved ``Principal``, not merely rejected if called: an
        anonymous turn wastes no context on a tool it can never use, and the
        model never gets a round trip to discover that the hard way. Same
        ``ctx``/``requires_identity`` this registry already gates ``execute``
        on — no new concept.
        """
        identified = ctx is not None and ctx.principal is not None
        return [
            t.to_api()
            for t in self._tools.values()
            if identified or not t.requires_identity
        ]

    def label(self, name: str, args: dict[str, Any]) -> str:
        """What a UI should show while this call runs. An unknown tool still
        gets a label — the loop announces the call before `execute` has had a
        chance to reject it."""
        tool = self._tools.get(name)
        return tool.label(args) if tool else _derive_label(name)

    async def execute(
        self, name: str, args: dict[str, Any], ctx: ToolContext | None = None
    ) -> str:
        """Run one tool call safely: the model observes errors as text instead
        of crashing the loop (execute_tool_safely pattern).

        ``ctx`` is opaque to every caller above this method (the loop only
        forwards it) — this is the one place that inspects it, so identity
        logic never leaks into ``run_loop`` or individual tool closures. A
        tool with ``requires_identity=True`` and no resolved ``Principal``
        is refused before ``fn`` ever runs.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        if tool.requires_identity and (ctx is None or ctx.principal is None):
            return (
                f"Error: {name} requires an identified user, but none is "
                "available for this conversation."
            )
        try:
            if tool.requires_identity or tool.needs_context:
                return await tool.fn(ctx=ctx, **args)
            return await tool.fn(**args)
        except Exception as exc:  # surface, don't crash — the model can retry
            return f"Error running {name}: {exc}"
