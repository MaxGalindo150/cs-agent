"""Unit tests for the retrieval gate (Level 1 — deterministic, fake LLM client).

The gate is one narrow decision made by a cheap model. We inject a fake
AsyncAnthropic whose `messages.create` returns a canned `Message` (a real SDK
pydantic type, like the loop tests) so we can assert on JSON parsing, the
reasoning-prose slice, and — most importantly — that the gate *fails open*.
"""

from __future__ import annotations

from typing import Any, cast

import anthropic
from anthropic.types import Message, TextBlock, Usage

from agent.memory.retrieval_gate import should_retrieve


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _msg(*blocks: Any) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=list(blocks),
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


class _FakeMessages:
    def __init__(self, response: Message | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class FakeClient:
    def __init__(self, response: Message | Exception) -> None:
        self.messages = _FakeMessages(response)


def _client(response: Message | Exception) -> anthropic.AsyncAnthropic:
    return cast(anthropic.AsyncAnthropic, FakeClient(response))


async def test_retrieves_on_valid_true_json() -> None:
    client = _client(
        _msg(_text('{"retrieve": true, "query": "vpn error", "reason": "past setup"}'))
    )
    retrieve, query, reason = await should_retrieve(
        client, "fast", "sigue fallando la vpn"
    )
    assert retrieve is True
    assert query == "vpn error"
    assert reason == "past setup"


async def test_skips_on_valid_false_json() -> None:
    client = _client(
        _msg(_text('{"retrieve": false, "query": "", "reason": "greeting"}'))
    )
    retrieve, _query, _reason = await should_retrieve(client, "fast", "¡gracias!")
    assert retrieve is False


async def test_extracts_json_embedded_in_reasoning_prose() -> None:
    # Reasoning models emit a thinking block before the JSON; the gate slices
    # from the first `{` to the last `}`, so the prose is tolerated.
    text = (
        "The customer refers to a past issue, so history helps.\n"
        '{"retrieve": true, "query": "billing", "reason": "account question"}'
    )
    client = _client(_msg(_text(text)))
    retrieve, query, _ = await should_retrieve(client, "fast", "sobre mi factura")
    assert retrieve is True
    assert query == "billing"


async def test_fails_open_when_reply_has_no_json() -> None:
    client = _client(_msg(_text("thinking out loud with no json at all")))
    retrieve, query, reason = await should_retrieve(client, "fast", "hola")
    assert retrieve is True
    assert query == "hola"  # falls back to the raw message as the search query
    assert "no JSON" in reason


async def test_fails_open_when_client_raises() -> None:
    client = _client(RuntimeError("api down"))
    retrieve, query, reason = await should_retrieve(client, "fast", "hola")
    assert retrieve is True
    assert query == "hola"
    assert "failed open" in reason


async def test_calls_the_fast_model_with_the_message_in_the_prompt() -> None:
    fake = FakeClient(_msg(_text('{"retrieve": false}')))
    await should_retrieve(
        cast(anthropic.AsyncAnthropic, fake), "haiku-test", "¿dónde va mi pedido?"
    )
    call = fake.messages.calls[0]
    assert call["model"] == "haiku-test"
    assert "¿dónde va mi pedido?" in call["messages"][0]["content"]
