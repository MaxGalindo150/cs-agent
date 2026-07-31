"""Unit tests for the tool registry (Level 1 — deterministic, no LLM)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.tools.registry import Tool, ToolRegistry

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _tool(name: str, fn: Callable[..., Awaitable[str]]) -> Tool:
    return Tool(name=name, description="test tool", input_schema=_SCHEMA, fn=fn)


async def test_execute_runs_the_tool_and_returns_its_string() -> None:
    async def echo(text: str) -> str:
        return f"echo:{text}"

    reg = ToolRegistry()
    reg.register(_tool("echo", echo))

    assert await reg.execute("echo", {"text": "hi"}) == "echo:hi"


async def test_unknown_tool_returns_error_instead_of_raising() -> None:
    reg = ToolRegistry()

    assert await reg.execute("nope", {}) == "Error: unknown tool 'nope'"


async def test_tool_that_raises_is_surfaced_as_text() -> None:
    async def boom() -> str:
        raise RuntimeError("kaboom")

    reg = ToolRegistry()
    reg.register(_tool("boom", boom))

    out = await reg.execute("boom", {})

    assert out.startswith("Error running boom:")
    assert "kaboom" in out


async def _noop() -> str:
    return "x"


def _labelled(name: str, progress_label: str | None) -> Tool:
    return Tool(
        name=name,
        description="test tool",
        input_schema=_SCHEMA,
        fn=_noop,
        progress_label=progress_label,
    )


def test_progress_label_interpolates_call_arguments() -> None:
    tool = _labelled("get_order", "Getting order {order_id}")

    assert tool.label({"order_id": "ord_1"}) == "Getting order ord_1"


def test_progress_label_survives_a_missing_argument() -> None:
    """The model can omit an optional argument; the label must degrade, not
    raise, and must not leave a dangling gap."""
    tool = _labelled("get_order", "Getting order {order_id}")

    assert tool.label({}) == "Getting order"


def test_progress_label_ignores_format_specs_in_arguments() -> None:
    """Placeholders are substituted, never formatted — so nothing the model
    puts in an argument is interpreted as a format spec."""
    tool = _labelled("get_order", "Getting order {order_id}")

    assert tool.label({"order_id": "{0.__class__}"}) == "Getting order {0.__class__}"


def test_label_is_derived_from_the_name_when_undeclared() -> None:
    assert _labelled("list_payment_methods", None).label({}) == (
        "Listing payment methods"
    )


def test_label_falls_back_to_the_bare_name_for_an_unknown_verb() -> None:
    """No invented verb: a name that does not follow `verb_noun` is spelled out
    as-is rather than mislabelled."""
    assert _labelled("frobnicate_thing", None).label({}) == "frobnicate thing"
    assert _labelled("ping", None).label({}) == "ping"


def test_registry_labels_an_unregistered_tool() -> None:
    """The loop announces a call before `execute` can reject it, so labelling
    must not depend on the tool existing."""
    assert ToolRegistry().label("get_order", {"order_id": "x"}) == "Getting order"


def test_schemas_expose_the_api_shape() -> None:
    async def t() -> str:
        return "x"

    reg = ToolRegistry()
    reg.register(_tool("t", t))

    assert reg.schemas() == [
        {"name": "t", "description": "test tool", "input_schema": _SCHEMA}
    ]
