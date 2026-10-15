"""Follow-up replies the aliado can tap instead of typing.

The model calls ``suggest_replies`` alone, after its answer; the chat draws
the options as buttons under the reply, and tapping one sends it as the
aliado's next message. The call ends the turn (``Tool.ends_turn``): the
reply is already written, so another LLM round trip would only add latency.
Silent: it isn't a step the aliado needs to see.
"""

from __future__ import annotations

import json
from typing import Any

from agent.tools.context import ToolContext
from agent.tools.registry import Tool

_MAX_OPTIONS = 3
_MAX_CHARS = 40


def make_suggest_replies_tool() -> Tool:
    async def suggest_replies(
        ctx: ToolContext, options: list[str] | None = None
    ) -> str:
        return json.dumps({"options": _clean(options)}, ensure_ascii=False)

    return Tool(
        name="suggest_replies",
        description=(
            "Offer up to 3 short follow-ups the aliado is likely to want next, "
            "as buttons under your answer (e.g. 'Ver detalle de la 924141', "
            "'¿Puedo cancelarla?'). Written as the aliado would say them, in "
            f"their language, {_MAX_CHARS} characters max each. Call it alone, "
            "after your answer is complete, and only when there's a natural "
            "next step; never to ask them something you need (just ask)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": _MAX_CHARS},
                    "minItems": 1,
                    "maxItems": _MAX_OPTIONS,
                }
            },
            "required": ["options"],
        },
        fn=suggest_replies,
        display=_display,
        silent=True,
        ends_turn=True,
        needs_context=True,
        audiences=frozenset({"merchant"}),
    )


def _clean(options: Any) -> list[str]:
    if not isinstance(options, list):
        return []
    cleaned = [o.strip() for o in options if isinstance(o, str) and o.strip()]
    return [o[:_MAX_CHARS] for o in cleaned][:_MAX_OPTIONS]


def _display(output: str) -> dict[str, Any] | None:
    options = json.loads(output).get("options") or []
    return {"type": "suggestions", "options": options} if options else None
