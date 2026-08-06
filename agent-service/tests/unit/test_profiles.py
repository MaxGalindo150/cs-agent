"""The profile registry contract (agent/profiles/).

These lock the properties that make "add an audience = add a module" true, so
the next profile cannot half-land: every registered profile must carry a soul,
name a config field that actually exists, and resolve its own identity headers.
"""

from __future__ import annotations

import pytest

from agent.profiles import DEFAULT_PROFILE, PROFILES, get_profile
from agent.prompts import load_prompt
from service.core.config import Settings


def test_every_profile_carries_a_non_empty_soul() -> None:
    for name, profile in PROFILES.items():
        assert profile.soul.strip(), f"{name} has an empty soul"


def test_every_profile_names_an_existing_settings_field() -> None:
    """`backend_url_setting` is a string because `agent/` must not import
    `Settings` — so a typo would only surface at boot. This is that guard."""
    settings = Settings(ENVIRONMENT="dev")
    for name, profile in PROFILES.items():
        assert hasattr(settings, profile.backend_url_setting), (
            f"{name} points at Settings.{profile.backend_url_setting}, which does "
            "not exist"
        )


def test_profile_names_match_their_registry_key() -> None:
    for name, profile in PROFILES.items():
        assert profile.name == name


@pytest.mark.parametrize("name", ["buyer", "merchant"])
def test_known_profiles_resolve(name: str) -> None:
    assert get_profile(name).name == name


@pytest.mark.parametrize("name", [None, "", "nope", "MERCHANT"])
def test_unknown_profile_falls_back_to_the_default(name: str | None) -> None:
    """The header is attacker-supplied: a bad value must not 500, and falling
    back to the buyer profile is the safe direction (merchant tools need a
    merchant principal, which buyer headers cannot produce)."""
    assert get_profile(name).name == DEFAULT_PROFILE


def test_buyer_reads_its_own_identity_headers() -> None:
    principal = get_profile("buyer").principal_from_headers(
        {"x-user-id": "usr_0001", "x-user-email": "alice@example.com"}
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email == "alice@example.com"
    assert principal.merchant_id is None


def test_merchant_reads_its_own_identity_headers() -> None:
    principal = get_profile("merchant").principal_from_headers(
        {"x-merchant-id": "1", "x-employee-id": "emp_0001"}
    )

    assert principal is not None
    assert principal.profile == "merchant"
    assert principal.merchant_id == "1"
    assert principal.employee_id == "emp_0001"
    # Synthetic id so merchant conversations never collide with buyer ones.
    assert principal.user_id == "merchant:1"


def test_a_profile_ignores_the_other_profiles_headers() -> None:
    """Cross-profile headers must not resolve: a buyer header set on the
    merchant profile leaves the merchant tools unavailable, and vice versa."""
    assert (
        get_profile("merchant").principal_from_headers({"x-user-id": "usr_1"}) is None
    )
    assert get_profile("buyer").principal_from_headers({"x-merchant-id": "1"}) is None


def test_souls_come_from_their_prompt_files() -> None:
    """The soul is the file's content, not a copy drifting inside a module."""
    for name, profile in PROFILES.items():
        assert profile.soul == load_prompt(name)


def test_load_prompt_rejects_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="no prompt named"):
        load_prompt("does-not-exist")
