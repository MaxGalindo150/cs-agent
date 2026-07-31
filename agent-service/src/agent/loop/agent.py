"""THE LOOP - observe -> reason -> act repeat. This file is the whole trick.

Every agent framework is ultimately this while-loop with more indirection:

    while not done:
        response = llm(messages, tools)      # resons
        if response asks for tools:
            results = run(tool_calls)        # act
            messages += results              # observe
        else:
            done                             # reply to the human

End-loop guardials (the orange box's exit conditions):
 1. the model stops asking for tools  -> natural end of turn
 2. max_iterations reached            -> hard stop, never spin forever
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, cast

import anthropic
from anthropic import APIError
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)

# Observers let the gateway show tool calls live and let ops/tracing record
# them - without either being wired into the loop's logic. Defined in
# agent.observability so every layer that emits events shares one signature.
from agent.observability import LoopEvent, Observer
from agent.tools.context import ToolContext
from agent.tools.registry import ToolRegistry


@dataclass
class LoopResult:
    reply: str
    tool_calls: list[LoopEvent] = field(default_factory=list)
    iterations: int = 0


async def run_loop(
    client: anthropic.AsyncAnthropic,
    model: str,
    system: str,
    messages: list[MessageParam],
    tools: ToolRegistry,
    max_iterations: int = 10,
    max_tokens: int = 2048,
    observer: Observer | None = None,
    stream: bool = False,
    ctx: ToolContext | None = None,
) -> LoopResult:
    """Run one agent turn. `messages` is mutated in place - after the call it
    contains the full working memory of the turn (assistant thoughts, tool
    calls, tool results), which is exactly what gets traced.

    stream=True emits the assistant's text as it's generated (notify("text",
    {"delta": ...})) so a gateway can show it appear token by token - used by
    the web UI. Falls back to a single call for clients without streaming.

    ``ctx`` is forwarded to ``tools.schemas``/``tools.execute`` untouched — the
    loop never reads it. Identity-gating (which tools the model even sees, and
    which calls are allowed to run) lives entirely in ``ToolRegistry``; these
    are the only two lines that touch ``ctx``, so business logic never leaks
    in here.
    """

    notify = observer or (lambda kind, ev: None)
    result = LoopResult(reply="")
    can_stream = stream and hasattr(client.messages, "stream")
    # The registry stays provider-neutral (plain dicts); adapt to the SDK's
    # ToolParam only here, at the Anthropic boundary.
    tool_schemas = cast("list[ToolParam]", tools.schemas(ctx))

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # ---- reason: one LLM call with the current working memory ----
        response: Message | None = None
        if can_stream:
            try:
                async with client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tool_schemas,
                    max_tokens=max_tokens,
                ) as s:
                    async for delta in s.text_stream:
                        notify("text", {"delta": delta})
                    response = await s.get_final_message()
            except (APIError, ConnectionError) as exc:
                # Surface the hiccup so tracing/ops see it, then fall back to a
                # single call. Auth/rate-limit/validation errors propagate: a
                # retry with the same request would just fail the same way.
                notify("stream_error", {"error": str(exc)})
                response = None
        if response is None:
            response = await client.messages.create(
                model=model,
                system=system,
                messages=messages,
                tools=tool_schemas,
                max_tokens=max_tokens,
            )
        notify(
            "llm",
            {
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "usage": {
                    "in": response.usage.input_tokens,
                    "out": response.usage.output_tokens,
                },
            },
        )

        # the assistant's turn (text and/or tool requests) joins working memory.
        # Output blocks fed back as input params — cast at the SDK boundary.
        messages.append(
            cast("MessageParam", {"role": "assistant", "content": response.content})
        )

        tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]

        # ---- guardrail 1: no tool calls -> the model is talking to the human
        if not tool_uses:
            result.reply = "".join(
                b.text for b in response.content if isinstance(b, TextBlock)
            )
            return result

        # ---- act: execute requested tools concurrently; observe: feed back.
        # Tools are independent (no shared mutable state in the registry), so a
        # batch of N calls takes one round-trip instead of N sequential ones.
        #
        # Announce the batch *before* running it: a tool can take seconds, and
        # the "tool" event below only fires once it has finished. Without this
        # a gateway could not show work in progress, only work already done —
        # and showing a live tool call is exactly what an observer is for.
        for call in tool_uses:
            args = cast("dict[str, Any]", call.input)
            notify(
                "tool_start",
                {
                    "tool": call.name,
                    "args": args,
                    # The tool words its own progress line (registry.Tool.label),
                    # so a client renders it without knowing the tool exists.
                    "label": tools.label(call.name, args),
                },
            )
        outputs = await asyncio.gather(
            *(tools.execute(call.name, call.input, ctx) for call in tool_uses)
        )
        tool_results: list[ToolResultBlockParam] = []
        for call, output in zip(tool_uses, outputs, strict=True):
            event = {"tool": call.name, "args": call.input, "output": output}
            result.tool_calls.append(event)
            notify("tool", event)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": output}
            )
        messages.append({"role": "user", "content": tool_results})

    notify("limit_reached", {"max_iterations": max_iterations})
    result.reply = (
        "(I hit my iteration limit before finishing - "
        "try breaking the request into smaller steps.)"
    )
    return result
