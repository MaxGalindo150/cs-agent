"""Prompts as files, versioned next to the code that uses them.

A soul is prose that changes on a different rhythm than the code around it, so
it lives in ``<name>.md`` here instead of a string literal inside a module.
Reviewing a persona change is then a diff of the prose alone, and nobody has to
re-indent a 40-line triple-quoted string to fix a sentence.

Read once at import by the profile that owns it (``agent/profiles/``), never
per turn.
"""

from __future__ import annotations

from importlib import resources


def load_prompt(name: str) -> str:
    """Return the text of ``<name>.md``, or raise if no such prompt exists."""
    prompt = resources.files(__package__).joinpath(f"{name}.md")
    if not prompt.is_file():
        raise ValueError(f"no prompt named {name!r} in agent/prompts/")
    return prompt.read_text(encoding="utf-8")
