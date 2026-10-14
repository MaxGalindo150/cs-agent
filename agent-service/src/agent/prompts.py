"""Prompts live as Markdown under agent-service/prompts/, not as Python strings.

Prompts are code (CLAUDE.md §7): versioned and reviewed like any other change,
but kept apart from the logic that uses them, so tuning wording never means
touching Python. Callers load them once at import, so a missing or empty file
stops the service at boot instead of serving a blank prompt; in dev, uvicorn
also reloads on *.md changes (see Dockerfile).

Files hold only static text. Per-turn values (the clock, who the caller is)
are appended by code, not templated in — that keeps the files editable without
knowing what the code substitutes, and the static prefix cacheable. The one
exception is the internal prompts' ``str.format`` fields (``{message}``,
``{log}``), whose literal braces are doubled, ``{{`` / ``}}``.
"""

from __future__ import annotations

from pathlib import Path

# agent-service/prompts — this file is agent-service/src/agent/prompts.py.
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


class PromptNotFound(RuntimeError):
    """A prompt file is missing or empty."""


def load_prompt(name: str) -> str:
    """The prompt at ``prompts/<name>.md``, e.g. ``"souls/consumer"``,
    without its trailing newline."""
    path = PROMPTS_DIR / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8").rstrip()
    except FileNotFoundError:
        raise PromptNotFound(f"missing prompt file: {path}") from None
    if not text:
        raise PromptNotFound(f"empty prompt file: {path}")
    return text
