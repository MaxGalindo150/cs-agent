"""Unit tests for the decision sites (Level 1 — deterministic, FakeDecider).

What is under test is the policy each site applies to a typed answer: the
confidence threshold, the fallback when the decider fails or is off, what
counts as "acted", and the shape of the ``decision`` trace record. Jev's own
accuracy is an eval concern (``evals/jev``), not a unit test.
"""

from __future__ import annotations

from typing import Any

from agent.decide.fake import FakeDecider, choice, noul, score
from agent.decide.sites import (
    DecisionConfig,
    Decisions,
    conversation_view,
    review_batch,
)

_TOOLS = [("search_orders", "search"), ("get_order_detail", "one order")]


class _Events:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def __call__(self, kind: str, event: dict[str, Any]) -> None:
        if kind == "decision":
            self.items.append(event)

    def only(self) -> dict[str, Any]:
        assert len(self.items) == 1, self.items
        return self.items[0]


# ---- disabled / fallback ------------------------------------------------------


async def test_disabled_decider_decides_nothing_and_traces_nothing() -> None:
    events = _Events()
    d = Decisions(None)

    assert not d.enabled
    assert await d.retrieval("hola", events) is None
    sel = await d.memory_select("m", ["a", "b"], events)
    assert sel.kept == ["a", "b"] and sel.source == "disabled"
    sk = await d.skill_match("m", [("x", "d")], ["x"], events)
    assert sk.skills == ["x"] and sk.source == "disabled"
    assert await d.tool_review([], "t", {}, _TOOLS, events) is None
    assert await d.ask_or_act([], "p", [], _TOOLS, events) is None
    assert (await d.consolidation_gate("log", events)).proceed
    assert await d.judge_turn("u", "r", [], [], "merchant", events) is None
    assert events.items == []


async def test_failed_call_falls_back_and_traces_the_error() -> None:
    events = _Events()
    d = Decisions(FakeDecider().fail(503))

    sel = await d.memory_select("m", ["a"], events)

    assert sel.kept == ["a"] and sel.source == "fallback"
    event = events.only()
    assert event["site"] == "memory_select"
    assert event["source"] == "fallback"
    assert event["acted"] is False
    assert "503" in event["error"]


# ---- retrieval ----------------------------------------------------------------


async def test_retrieval_records_the_kind_but_searches_both_stores() -> None:
    events = _Events()
    fake = FakeDecider().script(
        {"needs_history": noul(0.9), "memory_kind": choice("episodes", 0.95)}
    )
    verdict = await Decisions(fake).retrieval("sigue fallando", events)

    assert verdict is not None
    assert verdict.retrieve and verdict.episodes and verdict.facts
    event = events.only()
    assert event["answers"]["needs_history"] == {"type": "noul", "p": 0.9}
    assert event["verdict"] == {
        "retrieve": True,
        "kind": "episodes",
        "would_narrow": True,
    }


async def test_retrieval_unsure_kind_is_not_a_would_narrow() -> None:
    events = _Events()
    fake = FakeDecider().script(
        {"needs_history": noul(0.6), "memory_kind": choice("facts", 0.5)}
    )
    verdict = await Decisions(fake).retrieval("m", events)
    assert verdict is not None
    assert verdict.facts and verdict.episodes
    assert events.only()["verdict"]["would_narrow"] is False


async def test_retrieval_no_means_no_stores() -> None:
    fake = FakeDecider().script(
        {"needs_history": noul(0.1), "memory_kind": choice("facts", 0.99)}
    )
    verdict = await Decisions(fake).retrieval("gracias")
    assert verdict is not None
    assert not verdict.retrieve and not verdict.facts and not verdict.episodes


# ---- memory select ------------------------------------------------------------


async def test_memory_select_keeps_rows_at_or_above_half() -> None:
    events = _Events()
    fake = FakeDecider().script({"row_0": noul(0.5), "row_1": noul(0.2)})
    sel = await Decisions(fake).memory_select("m", ["keep", "drop"], events)

    assert sel.kept == ["keep"] and sel.dropped == 1
    assert events.only()["acted"] is True
    # the rows went to the decider as per-row questions over one state
    state, questions = fake.calls[0]
    assert state == {"message": "m"}
    assert set(questions) == {"row_0", "row_1"}


async def test_memory_select_with_no_rows_makes_no_call() -> None:
    fake = FakeDecider()
    sel = await Decisions(fake).memory_select("m", [])
    assert sel.kept == [] and fake.calls == []


# ---- skill match --------------------------------------------------------------


async def test_skill_match_confident_pick_replaces_keyword_baseline() -> None:
    events = _Events()
    fake = FakeDecider().script({"skill": choice("daily-closing", 0.97)})
    skills = [("daily-closing", "cierre de caja"), ("create-order", "crear orden")]

    verdict = await Decisions(fake).skill_match(
        "como cierro la caja", skills, baseline=["create-order"], notify=events
    )

    assert verdict.skills == ["daily-closing"]
    event = events.only()
    assert event["baseline"] == {"skills": ["create-order"]}
    assert event["agreement"] is False
    assert event["acted"] is True


async def test_skill_match_confident_none_loads_nothing() -> None:
    fake = FakeDecider().script({"skill": choice("none", 0.9)})
    verdict = await Decisions(fake).skill_match("hola", [("x", "d")], baseline=["x"])
    assert verdict.skills == []


async def test_skill_match_unsure_keeps_keyword_baseline() -> None:
    events = _Events()
    fake = FakeDecider().script({"skill": choice("x", 0.55, y=0.45)})
    verdict = await Decisions(fake).skill_match(
        "m", [("x", "d"), ("y", "e")], baseline=["y"], notify=events
    )
    assert verdict.skills == ["y"]
    assert events.only()["acted"] is False
    assert events.only()["agreement"] is True


# ---- tool review --------------------------------------------------------------


async def test_tool_review_suggests_only_for_a_confident_misfit() -> None:
    events = _Events()
    fake = FakeDecider().script(
        {
            "fits": noul(0.1),
            "best_tool": choice("get_order_detail", 0.93),
            "risk": score(0, 1.0),
        }
    )
    review = await Decisions(fake).tool_review(
        [{"role": "user", "content": "detalle de la 924141"}],
        "search_orders",
        {"status": "all"},
        _TOOLS,
        events,
    )

    assert review is not None and review.suggestion is not None
    assert "get_order_detail" in review.suggestion
    assert "call it again" in review.suggestion
    event = events.only()
    assert event["tool"] == "search_orders"
    assert event["verdict"]["misfit"] is True
    assert event["acted"] is True


async def test_tool_review_fit_call_runs_silently() -> None:
    fake = FakeDecider().script(
        {
            "fits": noul(0.95),
            "best_tool": choice("search_orders", 1.0),
            "risk": score(0, 1.0),
        }
    )
    review = await Decisions(fake).tool_review([], "search_orders", {}, _TOOLS)
    assert review is not None and review.suggestion is None


async def test_tool_review_unsure_best_tool_never_nudges() -> None:
    fake = FakeDecider().script(
        {"fits": noul(0.2), "best_tool": choice("reply", 0.6), "risk": score(0, 1.0)}
    )
    review = await Decisions(fake).tool_review([], "search_orders", {}, _TOOLS)
    assert review is not None and review.suggestion is None


async def test_review_batch_reviews_every_call() -> None:
    fake = (
        FakeDecider()
        .script({"fits": noul(0.9), "best_tool": choice("a", 1.0), "risk": score(0, 1)})
        .script({"fits": noul(0.9), "best_tool": choice("b", 1.0), "risk": score(0, 1)})
    )
    reviews = await review_batch(
        Decisions(fake), [], [("a", {}), ("b", {})], [("a", ""), ("b", "")]
    )
    assert [r.tool for r in reviews if r] == ["a", "b"]


# ---- ask or act ---------------------------------------------------------------


async def test_ask_or_act_confident_act_suggests_once_text() -> None:
    fake = FakeDecider().script({"action": choice("act", 0.9)})
    verdict = await Decisions(fake).ask_or_act(
        [], "¿Cuál orden?", [{"id": "a", "label": "la 1"}], _TOOLS
    )
    assert verdict is not None and verdict.action == "act"
    assert verdict.suggestion is not None and "present_choice" in verdict.suggestion


async def test_ask_or_act_ask_or_unsure_lets_the_question_through() -> None:
    d = Decisions(
        FakeDecider()
        .script({"action": choice("ask", 0.9)})
        .script({"action": choice("act", 0.6)})
    )
    first = await d.ask_or_act([], "p", [], _TOOLS)
    second = await d.ask_or_act([], "p", [], _TOOLS)
    assert first is not None and first.suggestion is None
    assert second is not None and second.suggestion is None


# ---- consolidation ------------------------------------------------------------


async def test_consolidation_gate_skips_only_clearly_empty_logs() -> None:
    d = Decisions(
        FakeDecider().script({"worth_it": noul(0.1)}).script({"worth_it": noul(0.35)})
    )
    assert not (await d.consolidation_gate("hola / hola")).proceed
    assert (await d.consolidation_gate("tengo un problema")).proceed


async def test_consolidation_gate_bounds_a_long_log_to_its_tail() -> None:
    fake = FakeDecider().script({"worth_it": noul(0.9)})
    d = Decisions(fake, DecisionConfig(max_state_chars=100))
    log = "\n".join(f"user: mensaje {i}" for i in range(200))
    assert (await d.consolidation_gate(log)).proceed
    state, _ = fake.calls[0]
    assert isinstance(state, str)
    assert state.startswith("[earlier exchanges omitted]\n")
    assert state.endswith("user: mensaje 199")
    assert len(state) <= 100 + len("[earlier exchanges omitted]\n")


async def test_fact_select_drops_facts_the_decider_rejects() -> None:
    fake = FakeDecider().script({"fact_0": noul(0.9), "fact_1": noul(0.1)})
    facts = [{"subject": "plan", "content": "Pro"}, {"subject": "x", "content": "hola"}]
    sel = await Decisions(fake).fact_select(facts, existing=["[plan] Basic"])
    assert sel.kept == [facts[0]] and sel.dropped == 1
    state, _ = fake.calls[0]
    assert isinstance(state, dict)
    assert state["already_stored"] == ["[plan] Basic"]


# ---- judge & diagnose ---------------------------------------------------------


async def test_judge_flags_llm_escalation_when_quality_is_unsure() -> None:
    events = _Events()
    fake = FakeDecider().script(
        {
            "quality": score(2, 0.55, levels=5),
            "grounded": noul(0.9),
            "resolved": noul(0.4),
        }
    )
    verdict = await Decisions(fake).judge_turn(
        "u", "r", [], ["daily-closing"], "merchant", events
    )
    assert verdict is not None
    assert verdict.needs_llm_judge
    assert verdict.quality == 2
    assert events.only()["verdict"]["resolved"] is False


async def test_judge_reads_confidence_as_mass_around_the_expected_level() -> None:
    # "good or excellent" (0.45/0.55): Jev's own confidence is 0.55, but
    # the answer is not in doubt — no escalation.
    adjacent = FakeDecider().script(
        {
            "quality": score(
                3.55, 0.55, levels=5, probabilities={"3": 0.45, "4": 0.55}
            ),
            "grounded": noul(0.9),
            "resolved": noul(0.9),
        }
    )
    verdict = await Decisions(adjacent).judge_turn("u", "r", [], [], "consumer")
    assert verdict is not None and not verdict.needs_llm_judge
    assert verdict.quality_confidence == 1.0

    # "wrong or good" (0.35 on 0, 0.48 on 3): the one case worth a second
    # opinion, and the one the top-level probability cannot flag.
    bimodal = FakeDecider().script(
        {
            "quality": score(
                2.04,
                0.48,
                levels=5,
                probabilities={"0": 0.35, "2": 0.04, "3": 0.48, "4": 0.13},
            ),
            "grounded": noul(0.5),
            "resolved": noul(0.5),
        }
    )
    verdict = await Decisions(bimodal).judge_turn("u", "r", [], [], "consumer")
    assert verdict is not None and verdict.needs_llm_judge
    assert round(verdict.quality_confidence, 2) == 0.52  # levels 1–3 around 2


async def test_judge_confident_does_not_escalate() -> None:
    fake = FakeDecider().script(
        {
            "quality": score(4, 0.95, levels=5),
            "grounded": noul(0.9),
            "resolved": noul(0.9),
        }
    )
    verdict = await Decisions(fake).judge_turn("u", "r", [], [], "merchant")
    assert verdict is not None and not verdict.needs_llm_judge


async def test_diagnose_labels_only_when_confident() -> None:
    d = Decisions(
        FakeDecider()
        .script({"failure_site": choice("tool_choice", 0.9), "actionable": noul(0.8)})
        .script({"failure_site": choice("tool_choice", 0.5), "actionable": noul(0.8)})
    )
    sure = await d.diagnose("u", "r", [], [], None)
    unsure = await d.diagnose("u", "r", [], [], "mal")
    assert sure is not None and sure.failure_site == "tool_choice"
    assert unsure is not None and unsure.failure_site is None


async def test_skill_proposal_needs_all_three_gates() -> None:
    d = Decisions(
        FakeDecider()
        .script({"recurring": noul(0.9), "duplicate": noul(0.1), "safe": noul(0.9)})
        .script({"recurring": noul(0.9), "duplicate": noul(0.7), "safe": noul(0.9)})
    )
    ok = await d.review_skill_proposal("n", "d", "b", [], [])
    dup = await d.review_skill_proposal("n", "d", "b", [], [])
    assert ok.approved and not dup.approved
    assert not (
        await Decisions(None).review_skill_proposal("n", "d", "b", [], [])
    ).approved


# ---- threshold & state view ---------------------------------------------------


async def test_threshold_is_configurable() -> None:
    fake = FakeDecider().script({"skill": choice("x", 0.7)})
    verdict = await Decisions(
        fake, DecisionConfig(confidence_threshold=0.6)
    ).skill_match("m", [("x", "d")], baseline=[])
    assert verdict.skills == ["x"]


def test_conversation_view_is_text_only_truncated_and_windowed() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "old"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "hola"}, {"type": "image"}],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "search_orders", "input": {"q": 1}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "content": "x" * 50}],
        },
    ]
    view = conversation_view(messages, window=3, max_chars=30)
    assert [v["role"] for v in view] == ["user", "assistant", "user"]
    assert view[0]["content"] == "hola [image]"
    assert view[1]["content"].startswith("[tool_use search_orders")
    assert view[2]["content"].endswith("…") and len(view[2]["content"]) == 30
