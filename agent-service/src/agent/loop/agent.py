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
    # The turn's text and tool-call groups, in the order they actually
    # happened — e.g. [text, tools, text] for "I'll escalate this" ->
    # escalate_to_human -> "Done, a person will follow up". `reply` alone
    # collapses that back to one string (for callers that just want the
    # final answer); this is what lets a client render the tool activity
    # between the two sentences instead of hoisting it above both.
    segments: list[LoopEvent] = field(default_factory=list)
    suspended: dict[str, Any] | None = None
    """Set when this turn stopped on a suspending tool call (``Tool.suspends``)
    instead of a natural end — everything ``Agent.respond()`` needs to hand to
    ``SessionRepository.set_suspended_tool_use``:
    ``{tool_use_id, tool_name, system, payload, iteration}``. ``turn_tail`` is
    filled in by the caller, which knows where ``session.history`` ends within
    ``messages`` — this loop doesn't."""


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
        text = "".join(b.text for b in response.content if isinstance(b, TextBlock))

        # ---- guardrail 1: no tool calls -> the model is talking to the human
        if not tool_uses:
            if text:
                result.segments.append({"type": "text", "text": text})
            result.reply = "\n\n".join(
                seg["text"] for seg in result.segments if seg["type"] == "text"
            )
            return result

        # A model can talk before it acts ("Voy a escalar esto...") in the same
        # response that asks for a tool — capture that lead-in as its own
        # segment now, before the tool group, so it keeps its place in order.
        if text:
            result.segments.append({"type": "text", "text": text})

        # ---- guardrail 2 (sort of): a suspending tool call pauses the turn.
        # `present_choice` is the first of these — the loop must not call the
        # LLM again this iteration, or the model would have to guess what the
        # customer will answer instead of actually waiting for it.
        suspending = [c for c in tool_uses if tools.suspends(c.name)]

        if suspending and len(tool_uses) > 1:
            # Anthropic requires every tool_use in this message to get a
            # tool_result before the message list is valid again, and a
            # suspending call can't share a batch with others (nothing here
            # could stay "pending" while its batch-mates already got real
            # results) — refuse the whole batch rather than run some tools and
            # strand the rest.
            refusals: list[ToolResultBlockParam] = [
                {
                    "type": "tool_result",
                    "tool_use_id": c.id,
                    "content": (
                        f"Error: {c.name} must be the only tool call in its "
                        "turn when a suspending tool is involved — retry it "
                        "alone."
                    ),
                }
                for c in tool_uses
            ]
            messages.append({"role": "user", "content": refusals})
            result.segments.append(
                {
                    "type": "tools",
                    "calls": [
                        {
                            "tool": c.name,
                            "args": c.input,
                            "output": r["content"],
                            "label": tools.label(
                                c.name, cast("dict[str, Any]", c.input)
                            ),
                        }
                        for c, r in zip(tool_uses, refusals, strict=True)
                    ],
                }
            )
            continue

        if suspending:
            call = suspending[0]  # exactly one — the mixed-batch case above handles >1
            args = cast("dict[str, Any]", call.input)
            notify(
                "tool_start",
                {
                    "tool": call.name,
                    "args": args,
                    "label": tools.label(call.name, args),
                },
            )
            output = await tools.execute(call.name, call.input, ctx)
            event = {"tool": call.name, "args": args, "output": output}
            result.tool_calls.append(event)
            notify("tool", event)
            prompt = args.get("prompt", "")
            options = args.get("options", [])
            notify("choice", {"prompt": prompt, "options": options})
            result.segments.append(
                {"type": "choice", "prompt": prompt, "options": options}
            )
            result.suspended = {
                "tool_use_id": call.id,
                "tool_name": call.name,
                "system": system,
                "payload": args,
                "iteration": iteration,
            }
            # Lead-in text (if any) plus the prompt itself — this is the
            # customer-facing reply for this half of the turn, same idea as
            # the no-tool-calls case joining every text segment.
            texts = [seg["text"] for seg in result.segments if seg["type"] == "text"]
            if prompt:
                texts.append(prompt)
            result.reply = "\n\n".join(texts)
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
        calls: list[LoopEvent] = []
        for call, output in zip(tool_uses, outputs, strict=True):
            args = cast("dict[str, Any]", call.input)
            event = {"tool": call.name, "args": args, "output": output}
            result.tool_calls.append(event)
            notify("tool", event)
            calls.append({**event, "label": tools.label(call.name, args)})
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": output}
            )
        result.segments.append({"type": "tools", "calls": calls})
        messages.append({"role": "user", "content": tool_results})

    notify("limit_reached", {"max_iterations": max_iterations})
    result.reply = (
        "(I hit my iteration limit before finishing - "
        "try breaking the request into smaller steps.)"
    )
    result.segments.append({"type": "text", "text": result.reply})
    return result
