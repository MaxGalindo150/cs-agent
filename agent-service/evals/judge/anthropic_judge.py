"""A DeepEval judge model backed by the same Anthropic API this service uses —
no separate OpenAI key needed for judging. Ported from Waku's
``evals/judge/anthropic_judge.py``; the only real difference is the client:
DeepEval's ``generate()`` is sync, but the app's own client is
``AsyncAnthropic`` (CLAUDE.md's async-everywhere rule), so the judge gets its
own plain sync ``anthropic.Anthropic`` — evaluation-only, never used to serve
a real turn.

DeepEval calls generate() with an optional pydantic schema when it wants
structured verdicts; we ask the model for JSON and validate it back.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import anthropic
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

from service.core.config import get_settings

_Schema = TypeVar("_Schema", bound=BaseModel)

# deepeval ships no py.typed marker (pyproject.toml's mypy override treats it
# as ignore_missing_imports, not fully unstubbed) — its own ABC types
# `__init__`/`load_model`/`model` loosely (bare *args/**kwargs, a `self.model`
# whose declared type is `DeepEvalBaseLLM` itself). Waku's version (which
# doesn't run mypy at all) skips `super().__init__()` outright and reuses
# `self.model` for the model *id* instead — the same shape here, with the
# resulting mismatches against deepeval's own loose typing suppressed at
# each specific line rather than papered over with a module-wide ignore.


class AnthropicJudge(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model: str = model or settings.anthropic_fast_model  # type: ignore[assignment]

    def load_model(self) -> anthropic.Anthropic:  # type: ignore[override]
        return self.client

    def generate(self, prompt: str, schema: type[_Schema] | None = None) -> Any:
        if schema is not None:
            prompt += (
                "\n\nReply with ONLY a JSON object matching this schema, no prose:\n"
                + json.dumps(schema.model_json_schema())
            )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        if schema is not None:
            body = text[text.index("{") : text.rindex("}") + 1]
            return schema.model_validate_json(body)
        return text

    async def a_generate(self, prompt: str, schema: type[_Schema] | None = None) -> Any:
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return f"AnthropicJudge({self.model})"
