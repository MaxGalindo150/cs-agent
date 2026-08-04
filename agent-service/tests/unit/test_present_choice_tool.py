"""Unit tests for the present_choice tool (Level 1 — no DB, no LLM).

`present_choice` is the first consumer of the suspended-tool-call primitive
(``Tool.suspends``): it does no lookup of its own, and the harness — not the
tool's own return string — is what makes the turn actually pause. These tests
only cover the tool's static metadata and its fixed acknowledgement; the
pausing behaviour itself is `test_loop.py`'s job, and persisting/resuming the
suspension is `test_respond.py`'s.
"""

from __future__ import annotations

from agent.tools.context import ToolContext
from agent.tools.implementations.present_choice import make_present_choice_tool


def test_tool_suspends_and_needs_context_without_identity() -> None:
    tool = make_present_choice_tool()

    assert tool.suspends is True
    assert tool.needs_context is True
    assert tool.requires_identity is False


def test_tool_schema_requires_prompt_and_two_to_four_options() -> None:
    schema = make_present_choice_tool().input_schema

    assert schema["required"] == ["prompt", "options"]
    assert schema["properties"]["options"]["minItems"] == 2
    assert schema["properties"]["options"]["maxItems"] == 4


async def test_fn_returns_a_fixed_acknowledgement() -> None:
    """The fn's own return value is never what makes the turn pause — that's
    the harness's job (Tool.suspends, run_loop's suspend branch) — so it
    doesn't need to do anything with its arguments."""
    ctx = ToolContext(principal=None)

    out = await make_present_choice_tool().fn(
        ctx, prompt="Card or credit?", options=[{"id": "a", "label": "Card"}]
    )

    assert "paused" in out
