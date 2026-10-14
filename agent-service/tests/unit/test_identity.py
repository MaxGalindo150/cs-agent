"""Unit tests for the identity seam (service/core/identity.py).

Under test, in resolution order: a Bearer session token is verified (and a bad
one is a 401, never anonymous); otherwise the X-User-Id/X-User-Email headers
are trusted only in dev; otherwise the caller is anonymous.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from agent.identity import Principal
from service.core import session_token
from service.core.config import Settings
from service.core.identity import get_principal

_KEY = "test-signing-key-with-enough-entropy-0123456789"


def _settings(environment: str, signing_key: str = _KEY) -> Settings:
    # Settings' fields are alias-only (no populate_by_name) — ENVIRONMENT is
    # the wire name, not the Python attribute (see service/core/config.py).
    return Settings(ENVIRONMENT=environment, SESSION_SIGNING_KEY=signing_key)


def _bearer(principal: Principal, key: str = _KEY, ttl: int = 60) -> str:
    return f"Bearer {session_token.issue(principal, key, ttl)}"


# --- Bearer session token ---------------------------------------------------


def test_valid_bearer_resolves_the_full_principal() -> None:
    issued = Principal(
        user_id="uid_1",
        email="aliado@example.com",
        merchant_id="42",
        store_id="7",
        role="admin",
    )

    principal = get_principal(
        settings=_settings("staging"),
        authorization=_bearer(issued),
        x_user_id=None,
        x_user_email=None,
    )

    assert principal == issued


def test_bearer_wins_over_dev_headers() -> None:
    principal = get_principal(
        settings=_settings("dev"),
        authorization=_bearer(Principal(user_id="uid_1")),
        x_user_id="usr_0001",
        x_user_email=None,
    )

    assert principal is not None
    assert principal.user_id == "uid_1"


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer not-a-jwt",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        _bearer(Principal(user_id="uid_1"), key="another-key-entirely-0123456789ab"),
        _bearer(Principal(user_id="uid_1"), ttl=-120),
    ],
    ids=["garbage", "empty", "wrong-scheme", "wrong-key", "expired"],
)
def test_bad_bearer_is_401_not_anonymous(authorization: str) -> None:
    # Falling back to anonymous would hide an expired token from the widget,
    # which relies on the 401 to know it must renew.
    with pytest.raises(HTTPException) as exc:
        get_principal(
            settings=_settings("dev"),
            authorization=authorization,
            x_user_id="usr_0001",
            x_user_email=None,
        )

    assert exc.value.status_code == 401


def test_bearer_is_rejected_when_no_signing_key_is_configured() -> None:
    with pytest.raises(HTTPException) as exc:
        get_principal(
            settings=_settings("staging", signing_key=""),
            authorization=_bearer(Principal(user_id="uid_1")),
            x_user_id=None,
            x_user_email=None,
        )

    assert exc.value.status_code == 401


# --- Dev-only trusted headers -----------------------------------------------


def test_dev_with_header_resolves_a_principal() -> None:
    principal = get_principal(
        settings=_settings("dev"),
        authorization=None,
        x_user_id="usr_0001",
        x_user_email="alice@example.com",
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email == "alice@example.com"


def test_dev_with_header_but_no_email_still_resolves() -> None:
    principal = get_principal(
        settings=_settings("dev"),
        authorization=None,
        x_user_id="usr_0001",
        x_user_email=None,
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email is None


def test_dev_without_header_resolves_to_none() -> None:
    principal = get_principal(
        settings=_settings("dev"), authorization=None, x_user_id=None, x_user_email=None
    )

    assert principal is None


def test_non_dev_ignores_the_header_even_when_present() -> None:
    # The trust-boundary relaxation is dev-only: staging/prod must fail closed.
    principal = get_principal(
        settings=_settings("staging"),
        authorization=None,
        x_user_id="usr_0001",
        x_user_email="alice@example.com",
    )

    assert principal is None


def test_environment_defaults_to_a_non_dev_value() -> None:
    """Fail-closed by construction: a deployment that omits ENVIRONMENT must
    not silently trust X-User-Id (or expose /docs) as if it were dev."""
    assert Settings.model_fields["environment"].default != "dev"
