"""Unit tests for the prompt loader (agent/prompts.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent import prompts
from agent.prompts import PromptNotFound, load_prompt


def test_loads_a_prompt_without_its_trailing_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "souls").mkdir()
    (tmp_path / "souls" / "x.md").write_text("Hola.\n\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)

    assert load_prompt("souls/x") == "Hola."


def test_missing_prompt_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)

    with pytest.raises(PromptNotFound, match="missing"):
        load_prompt("souls/nope")


def test_empty_prompt_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "blank.md").write_text("  \n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)

    with pytest.raises(PromptNotFound, match="empty"):
        load_prompt("blank")


@pytest.mark.parametrize(
    "name",
    ["souls/consumer", "internal/retrieval_gate", "internal/memory_summarizer"],
)
def test_shipped_prompts_exist(name: str) -> None:
    assert load_prompt(name)
