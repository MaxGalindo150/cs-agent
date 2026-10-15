"""Unit tests for propose_skill (Level 1 — fake memory, FakeDecider).

The tool validates the draft, asks the decision model its three questions
with the audience's catalogue and the recent conversation, traces the whole
proposal, and never makes the skill take effect.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from agent.decide.fake import FakeDecider, noul
from agent.decide.sites import Decisions
from agent.identity import Principal
from agent.memory import Memory
from agent.tools.context import ToolContext
from agent.tools.implementations.propose_skill import make_propose_skill_tool
from agent.tools.registry import ToolRegistry

_ALIADO = Principal(user_id="emp_1", merchant_id="42")


class _FakeMemory:
    def __init__(self) -> None:
        self.catalog_calls: list[str] = []

    def skill_catalog(self, audience: str) -> list[tuple[str, str]]:
        self.catalog_calls.append(audience)
        return [("daily-closing", "cierre de caja")]

    async def session_history(self, session_id: uuid.UUID) -> list[tuple[str, str]]:
        return [("¿cómo cambio el logo?", "No lo sé, ve al portal")]


def _tool(decider: FakeDecider | None) -> tuple[ToolRegistry, _FakeMemory]:
    memory = _FakeMemory()
    reg = ToolRegistry()
    reg.register(make_propose_skill_tool(cast(Memory, memory), Decisions(decider)))
    return reg, memory


def _ctx(events: list[tuple[str, dict[str, Any]]]) -> ToolContext:
    return ToolContext(
        principal=_ALIADO,
        session_id=uuid.uuid4(),
        notify=lambda k, e: events.append((k, e)),
    )


_ARGS = {
    "name": "Store Branding",
    "description": "Usar cuando el aliado pregunta cómo cambiar el logo o nombre.",
    "body": "# Branding\n1. Ir a Configuración.\n2. Subir el logo.",
}


async def test_approved_proposal_is_traced_and_never_takes_effect() -> None:
    fake = FakeDecider().script(
        {"recurring": noul(0.9), "duplicate": noul(0.1), "safe": noul(0.95)}
    )
    reg, memory = _tool(fake)
    events: list[tuple[str, dict[str, Any]]] = []

    out = await reg.execute("propose_skill", _ARGS, _ctx(events))

    assert "flagged it for human review" in out
    assert "does not take effect" in out
    assert memory.catalog_calls == ["merchant"]
    state, _ = fake.calls[0]
    assert isinstance(state, dict)
    assert state["proposal"]["name"] == "store-branding"
    assert state["existing_skills"] == [
        {"name": "daily-closing", "description": "cierre de caja"}
    ]
    assert state["conversation"][0]["content"] == "¿cómo cambio el logo?"
    proposal = [e for k, e in events if k == "skill_proposal"]
    assert proposal[0]["approved"] is True
    assert proposal[0]["body"] == _ARGS["body"]
    assert [e["site"] for k, e in events if k == "decision"] == ["skill_proposal"]


async def test_rejected_proposal_says_why() -> None:
    fake = FakeDecider().script(
        {"recurring": noul(0.9), "duplicate": noul(0.8), "safe": noul(0.9)}
    )
    reg, _ = _tool(fake)
    out = await reg.execute("propose_skill", _ARGS, _ctx([]))
    assert "not approved" in out and "existing skill already covers it" in out


async def test_without_a_decider_nothing_is_approved() -> None:
    reg, _ = _tool(None)
    events: list[tuple[str, dict[str, Any]]] = []
    out = await reg.execute("propose_skill", _ARGS, _ctx(events))
    assert "could not be pre-screened" in out
    assert [e for k, e in events if k == "skill_proposal"][0]["approved"] is False


async def test_invalid_or_duplicate_names_are_refused_before_any_decision() -> None:
    fake = FakeDecider()
    reg, _ = _tool(fake)
    assert "needs a name" in await reg.execute(
        "propose_skill", {**_ARGS, "body": ""}, _ctx([])
    )
    assert "already exists" in await reg.execute(
        "propose_skill", {**_ARGS, "name": "daily-closing"}, _ctx([])
    )
    assert "too long" in await reg.execute(
        "propose_skill", {**_ARGS, "body": "\n".join(["x"] * 61)}, _ctx([])
    )
    assert fake.calls == []
