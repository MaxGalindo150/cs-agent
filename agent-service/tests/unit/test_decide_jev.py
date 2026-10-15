"""Unit tests for the Jev wire client (Level 1 — deterministic, MockTransport).

What is under test is the contract we own: the request shape, the typed
parsing of answers, retries on the right statuses only, and that an error
never leaks the request body (customer text) into the exception message.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from agent.decide.jev import (
    Choice,
    Decision,
    JevClient,
    JevConfig,
    JevError,
    Noul,
    NoulCriteria,
    Question,
    Score,
)

_OK: dict[str, Any] = {
    "model": "jev-1.13.0",
    "answers": {
        "needs": {"type": "noul", "noul": 0.72},
        "kind": {
            "type": "choice",
            "choice": "get_order",
            "confidence": 0.95,
            "probabilities": {"get_order": 0.95, "search_orders": 0.05},
        },
        "risk": {
            "type": "score",
            "score": 0.0,
            "confidence": 1.0,
            "legend": {"0": "read", "1": "write"},
            "probabilities": {"0": 1.0, "1": 0.0},
        },
    },
    "usage": {"input_tokens": 400, "output_tokens": 80},
}

_QUESTIONS: dict[str, Question] = {
    "needs": Noul(instructions="needs history?", criteria=NoulCriteria(true="yes")),
    "kind": Choice(
        instructions="which tool", criteria={"get_order": "one", "search_orders": None}
    ),
    "risk": Score(instructions="risk", criteria=["read", "write"]),
}


def _client(
    handler: Any, max_retries: int = 1
) -> tuple[JevClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request, len(seen))  # type: ignore[no-any-return]

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(wrapped), base_url="http://jev.test"
    )
    return (
        JevClient(JevConfig(api_key="k", max_retries=max_retries), http=http),
        seen,
    )


async def test_request_shape_and_typed_answers() -> None:
    client, seen = _client(lambda r, n: httpx.Response(200, json=_OK))

    decision = await client.decide("state text", _QUESTIONS)

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/systemone"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert body["model"] == "jev-latest"
    assert body["state"] == "state text"
    # a Noul with no criteria sends none; a Choice option with no
    # description goes out as an explicit null, never dropped
    assert body["questions"]["kind"]["criteria"] == {
        "get_order": "one",
        "search_orders": None,
    }
    assert body["questions"]["risk"]["criteria"] == ["read", "write"]

    assert decision.noul("needs").noul == 0.72
    assert decision.noul("needs").yes
    assert decision.choice("kind").choice == "get_order"
    assert decision.score("risk").score == 0.0
    assert decision.usage.input_tokens == 400
    assert decision.latency_ms >= 0


async def test_typed_accessor_mismatch_is_a_programming_error() -> None:
    decision = Decision.model_validate(_OK)
    with pytest.raises(TypeError):
        decision.choice("needs")


def test_as_trace_keeps_the_raw_primitives() -> None:
    trace = Decision.model_validate(_OK).as_trace()
    assert trace["needs"] == {"type": "noul", "p": 0.72}
    assert trace["kind"]["choice"] == "get_order"
    assert trace["kind"]["probabilities"]["search_orders"] == 0.05
    assert trace["risk"]["score"] == 0.0


async def test_retries_once_on_503_then_succeeds() -> None:
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(503, headers={"retry-after-ms": "1"})
        return httpx.Response(200, json=_OK)

    client, seen = _client(handler)
    await client.decide("s", _QUESTIONS)
    assert len(seen) == 2


async def test_does_not_retry_a_4xx_and_reports_status_and_request_id() -> None:
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(
            403,
            json={"detail": {"error_type": "authentication_error", "message": "nope"}},
            headers={"x-typesafe-request-id": "req_1"},
        )

    client, seen = _client(handler)
    with pytest.raises(JevError) as err:
        await client.decide("customer secret text", _QUESTIONS)
    assert len(seen) == 1
    assert err.value.status == 403
    assert err.value.request_id == "req_1"
    assert "nope" in str(err.value)
    assert "customer secret text" not in str(err.value)


async def test_transport_error_exhausts_retries_into_jev_error() -> None:
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client, seen = _client(handler, max_retries=1)
    with pytest.raises(JevError) as err:
        await client.decide("s", _QUESTIONS)
    assert len(seen) == 2
    assert err.value.status is None


async def test_empty_questions_is_rejected_locally() -> None:
    client, seen = _client(lambda r, n: httpx.Response(200, json=_OK))
    with pytest.raises(ValueError):
        await client.decide("s", {})
    assert seen == []


def test_choice_and_score_bounds_fail_locally() -> None:
    with pytest.raises(ValueError):
        Choice(instructions="x", criteria={"only": None})
    with pytest.raises(ValueError):
        Score(instructions="x", criteria=["one"])
