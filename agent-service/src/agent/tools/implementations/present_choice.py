"""present_choice — pause the turn and let the customer pick between options.

The first (and, for now, only) consumer of the suspended-tool-call primitive
(``Tool.suspends``, ``agent/loop/agent.py``'s suspend branch): once called,
the harness stops the loop and persists everything needed to resume once the
customer answers, either by clicking one of the options or by typing instead
(``agent/app.py::Agent._resume_suspended_turn``). Like
``escalate_to_human``, ``needs_context=True`` rather than
``requires_identity=True`` — asking a clarifying question must keep working
for an anonymous visitor too.

This tool's own return value is never shown to the model in a way that lets
it keep reasoning this turn — the harness cuts the turn short right after
calling it — so the fn does no lookup and returns a fixed acknowledgement.
"""

from __future__ import annotations

from agent.tools.context import ToolContext
from agent.tools.registry import Tool


async def present_choice(
    ctx: ToolContext,
    prompt: str = "",
    options: list[dict[str, str]] | None = None,
) -> str:
    return (
        "Presented these options to the customer; the turn is paused until "
        "they answer — say nothing further right now."
    )


def make_present_choice_tool() -> Tool:
    return Tool(
        name="present_choice",
        description=(
            "Pause and show the customer 2-4 clickable options to choose "
            "between (e.g. 'Refund to the card or store credit?'). Call this "
            "ALONE — never alongside another tool call in the same turn; a "
            "mixed batch is rejected and you'll have to retry it by itself. "
            "The customer's answer (by clicking, or by typing instead) "
            "arrives as your next turn's tool result — wait for it, don't "
            "guess what they'll pick."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question to show the customer.",
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Stable identifier for this option.",
                            },
                            "label": {
                                "type": "string",
                                "description": "What the customer sees on the button.",
                            },
                        },
                        "required": ["id", "label"],
                    },
                    "description": "2 to 4 options the customer can pick from.",
                },
            },
            "required": ["prompt", "options"],
        },
        fn=present_choice,
        needs_context=True,
        suspends=True,
        progress_label="Asking the customer to choose",
    )
