"""Jev — the decision model behind the harness's judgment calls.

Jev (TypeSafe AI's "System One") generates no text. It takes a ``state`` (the
thing to judge) and typed ``questions``, and returns typed answers with
calibrated probabilities:

    noul    yes / no             -> P(yes)
    choice  one of N labels      -> label + distribution + confidence
    score   a level on a rubric  -> level + distribution + confidence

Why the harness wants this (CLAUDE.md §1, "the model reasons; the harness
guarantees"): the small decisions the harness makes on every turn — does
this message need memory, which skill applies, is this tool call the right
next step, is this reply any good — are narrow and typed. Asking the chat
model for them means a free-text answer we parse and cannot threshold on.
A Jev answer is schema-locked and its confidence is a probability, so the
harness can route on it: act when sure, fall back to what it did before
when not.

Called over plain ``httpx``, no vendor SDK — the same call the Voyage embedder
makes (agent/memory/embeddings.py): a ~100-line wire contract we can own and
test with ``MockTransport``. Wire reference: ``POST /v1/systemone``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

# What Jev accepts as a ``state`` and as free-form ``instructions``: text, or
# structured JSON (a chat log, a record, application state).
JSONContent = str | dict[str, Any] | list[Any]
State = JSONContent

# --- questions ----------------------------------------------------------------


class NoulCriteria(BaseModel):
    """Optional gloss for what a yes and a no mean."""

    model_config = ConfigDict(frozen=True)

    true: JSONContent | None = None
    false: JSONContent | None = None


class Noul(BaseModel):
    """A yes/no question. The answer is P(yes)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["noul"] = "noul"
    instructions: JSONContent
    criteria: NoulCriteria | None = None


class Choice(BaseModel):
    """Pick exactly one of ``criteria``'s keys. A ``None`` description means
    "read the label by its name alone"."""

    model_config = ConfigDict(frozen=True)

    type: Literal["choice"] = "choice"
    instructions: JSONContent
    criteria: dict[str, JSONContent | None]

    @field_validator("criteria")
    @classmethod
    def _bounded(
        cls, value: dict[str, JSONContent | None]
    ) -> dict[str, JSONContent | None]:
        # The API documents the cap but its schema doesn't enforce it: fail
        # here, locally, not as a remote 4xx mid-turn.
        if not 2 <= len(value) <= 255:
            raise ValueError("a Choice needs between 2 and 255 options")
        return value


class Score(BaseModel):
    """Rate the state on an ordered rubric; level ``i`` is ``criteria[i]``."""

    model_config = ConfigDict(frozen=True)

    type: Literal["score"] = "score"
    instructions: JSONContent
    criteria: list[JSONContent]

    @field_validator("criteria")
    @classmethod
    def _bounded(cls, value: list[JSONContent]) -> list[JSONContent]:
        if not 2 <= len(value) <= 10:
            raise ValueError("a Score needs between 2 and 10 levels")
        return value


Question = Noul | Choice | Score

# --- answers ------------------------------------------------------------------


class NoulAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    type: Literal["noul"]
    noul: float = Field(ge=0.0, le=1.0)

    @property
    def yes(self) -> bool:
        return self.noul >= 0.5


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)


class ScoreAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    type: Literal["score"]
    score: float
    legend: dict[str, JSONContent]
    probabilities: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    input_tokens: int
    output_tokens: int


class Decision(BaseModel):
    """One round-trip's typed answers, keyed by the caller's question names.

    The typed accessors fail loudly on a name/type mismatch: a site that asks
    a ``Noul`` and reads it as a ``Choice`` is a programming error, never
    something to paper over at runtime.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    model: str
    answers: dict[str, Answer]
    usage: Usage
    latency_ms: int = 0

    def noul(self, name: str) -> NoulAnswer:
        return self._typed(name, NoulAnswer)

    def choice(self, name: str) -> ChoiceAnswer:
        return self._typed(name, ChoiceAnswer)

    def score(self, name: str) -> ScoreAnswer:
        return self._typed(name, ScoreAnswer)

    def _typed[T: BaseModel](self, name: str, kind: type[T]) -> T:
        answer = self.answers[name]
        if not isinstance(answer, kind):
            raise TypeError(
                f"answer {name!r} is {type(answer).__name__}, not {kind.__name__}"
            )
        return answer

    def as_trace(self) -> dict[str, Any]:
        """The answers as flat JSON for a trace record — the primitives
        exactly as Jev returned them (probability / label + confidence /
        level + confidence), so a reader of the trace sees what the harness
        saw before it applied any threshold."""
        out: dict[str, Any] = {}
        for name, answer in self.answers.items():
            if isinstance(answer, NoulAnswer):
                out[name] = {"type": "noul", "p": round(answer.noul, 3)}
            elif isinstance(answer, ChoiceAnswer):
                out[name] = {
                    "type": "choice",
                    "choice": answer.choice,
                    "confidence": round(answer.confidence, 3),
                    "probabilities": {
                        k: round(v, 3) for k, v in answer.probabilities.items()
                    },
                }
            else:
                out[name] = {
                    "type": "score",
                    "score": round(answer.score, 3),
                    "confidence": round(answer.confidence, 3),
                    "probabilities": {
                        k: round(v, 3) for k, v in answer.probabilities.items()
                    },
                }
        return out


# --- the seam -----------------------------------------------------------------


class Decider(Protocol):
    """What the harness depends on. ``JevClient`` is the production one; tests
    and offline evals plug in ``agent.decide.fake.FakeDecider``. The harness
    never names ``JevClient`` directly, so the decision model can be swapped
    or removed without touching a decision site."""

    async def decide(
        self, state: State, questions: Mapping[str, Question]
    ) -> Decision: ...


class JevError(Exception):
    """A failed decision call: the HTTP status (``None`` for a transport
    failure) and the server's request id when it sent one, so an incident can
    be correlated on their side."""

    def __init__(
        self, message: str, *, status: int | None = None, request_id: str | None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class JevConfig:
    api_key: str
    model: str = "jev-latest"
    base_url: str = "https://api.typesafe.ai"
    timeout_s: float = 5.0
    """Hard ceiling per call. Jev answers in ~0.2–0.6 s; anything slower is an
    outage from the harness's point of view, and every site has a fallback —
    waiting longer only adds latency to the turn."""
    max_retries: int = 1
    """Retries on 408/429/5xx and transport errors only. One is enough on the
    request path: the sites fall back on their own, so we never stack
    retries on top of an already-slow turn."""


_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504, 529})
_BACKOFF_S = 0.5
_MAX_SERVER_DELAY_S = 5.0


class JevClient:
    """Async client for ``POST /v1/systemone``. Owns its ``httpx`` client
    unless one is injected (tests pass a ``MockTransport``-backed one)."""

    def __init__(
        self, config: JevConfig, http: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_s
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decision:
        if not questions:
            raise ValueError("at least one question is required")
        body = {
            "state": state,
            "model": self._config.model,
            "questions": {name: _dump(q) for name, q in questions.items()},
        }
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        t0 = time.perf_counter()
        attempt = 0
        while True:
            try:
                response = await self._http.post(
                    "/v1/systemone", json=body, headers=headers
                )
            except httpx.HTTPError as exc:
                if attempt >= self._config.max_retries:
                    raise JevError(
                        f"jev transport failure: {type(exc).__name__}",
                        request_id=None,
                    ) from exc
                attempt += 1
                await asyncio.sleep(_BACKOFF_S * attempt)
                continue

            request_id = response.headers.get("x-typesafe-request-id")
            if response.status_code < 300:
                decision = Decision.model_validate(response.json())
                return decision.model_copy(
                    update={"latency_ms": int((time.perf_counter() - t0) * 1000)}
                )
            if (
                response.status_code in _RETRYABLE
                and attempt < self._config.max_retries
            ):
                attempt += 1
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            raise JevError(
                f"jev returned HTTP {response.status_code}: {_error_detail(response)}",
                status=response.status_code,
                request_id=request_id,
            )


def _dump(question: Question) -> dict[str, Any]:
    """Wire form of a question. Only *top-level* ``None`` fields are dropped
    (an absent ``criteria`` on a Noul). Inside ``Choice.criteria`` a ``None``
    is meaningful — "this option has no description" — and must go out as
    ``null`` or the option would silently vanish from the verdict space."""
    return {
        key: value
        for key, value in question.model_dump(mode="json").items()
        if value is not None
    }


def _error_detail(response: httpx.Response) -> str:
    """The server's own error message, truncated. Never the request body: it
    carries customer text and this string lands in traces."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("error_type")
        if isinstance(message, str):
            return message[:200]
    return str(detail)[:200] if detail is not None else response.text[:200]


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honor ``retry-after-ms`` / ``retry-after`` when sent (capped), else a
    short linear backoff — this runs inside a customer's turn."""
    raw_ms = response.headers.get("retry-after-ms")
    raw_s = response.headers.get("retry-after")
    try:
        if raw_ms is not None:
            return min(int(raw_ms) / 1000, _MAX_SERVER_DELAY_S)
        if raw_s is not None:
            return min(float(raw_s), _MAX_SERVER_DELAY_S)
    except ValueError:
        pass
    return _BACKOFF_S * attempt
