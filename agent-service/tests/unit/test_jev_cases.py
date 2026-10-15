"""The labelled set for the decision sites (evals/jev/cases.jsonl) is data the
live replay and CI depend on: keep its shape honest, and keep every label
inside the catalogues the harness actually offers (a skill that doesn't
exist, a tool the aliado can't see) — a typo there would read as a model
miss in the report.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from agent.memory import REPO_SKILLS
from agent.memory.procedural.loader import SkillLoader

_CASES = Path(__file__).resolve().parents[2] / "evals" / "jev" / "cases.jsonl"
_MERCHANT_TOOLS = {
    "search_orders",
    "get_order_detail",
    "get_monthly_report",
    "get_daily_closing",
    "suggest_replies",
    "present_choice",
    "manage_memory",
    "reply",
}
_REQUIRED = {
    "retrieval": {"message"},
    "skill_match": {"message", "audience"},
    "tool_review": {"conversation", "call"},
    "ask_or_act": {"conversation", "prompt", "options"},
    "judge": {"user_message", "reply", "tools_used", "skills", "audience"},
    "fact_select": {"facts", "existing"},
    "consolidation_gate": {"log"},
}


def _cases() -> list[dict[str, object]]:
    return [
        json.loads(line) for line in _CASES.read_text().splitlines() if line.strip()
    ]


def test_every_case_has_its_sites_fields_and_a_unique_id() -> None:
    cases = _cases()
    ids = Counter(str(c["id"]) for c in cases)
    assert not [i for i, n in ids.items() if n > 1]
    for case in cases:
        site = str(case["site"])
        assert site in _REQUIRED, case["id"]
        assert _REQUIRED[site] <= set(case), case["id"]
        assert isinstance(case["expect"], dict) and case["expect"] != {}, case["id"]


def test_sites_have_enough_cases_to_mean_something() -> None:
    counts = Counter(str(c["site"]) for c in _cases())
    # the three sites that act on the request path need the most evidence
    for site in ("skill_match", "retrieval", "tool_review"):
        assert counts[site] >= 15, (site, counts[site])
    assert set(counts) == set(_REQUIRED)


def test_skill_labels_exist_in_the_merchant_catalogue() -> None:
    names = {s.name for s in SkillLoader([REPO_SKILLS / "merchant"]).skills}
    assert names, "no merchant skills found in skills/merchant"
    for case in _cases():
        if case["site"] != "skill_match":
            continue
        expect = case["expect"]
        assert isinstance(expect, dict)
        assert expect["skill"] is None or expect["skill"] in names, case["id"]


def test_tool_labels_are_tools_an_aliado_can_see() -> None:
    for case in _cases():
        expect = case["expect"]
        assert isinstance(expect, dict)
        if case["site"] == "tool_review":
            call = case["call"]
            assert isinstance(call, dict)
            assert call["tool"] in _MERCHANT_TOOLS, case["id"]
            assert expect["best_tool"] in _MERCHANT_TOOLS, case["id"]
        if case["site"] == "ask_or_act":
            assert expect["action"] in {"ask", "act"}, case["id"]
