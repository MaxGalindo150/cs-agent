"""Unit tests for agent.identity.audience_of."""

from __future__ import annotations

from agent.identity import Principal, audience_of


def test_a_merchant_employee_is_an_aliado() -> None:
    assert audience_of(Principal(user_id="uid_1", merchant_id="42")) == "merchant"


def test_everyone_else_is_a_consumer() -> None:
    assert audience_of(Principal(user_id="usr_1")) == "consumer"
    assert audience_of(None) == "consumer"
