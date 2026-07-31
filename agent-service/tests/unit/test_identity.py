"""Unit tests for the identity seam stub (service/core/identity.py).

STUB behavior under test: trust the X-User-Id/X-User-Email headers verbatim,
but only in dev — everywhere else, resolve to no Principal regardless of what
the caller sent. See the module docstring for why.
"""

from __future__ import annotations

from service.core.config import Settings
from service.core.identity import get_principal


def _settings(environment: str) -> Settings:
    # Settings' fields are alias-only (no populate_by_name) — ENVIRONMENT is
    # the wire name, not the Python attribute (see service/core/config.py).
    return Settings(ENVIRONMENT=environment)


def test_dev_with_header_resolves_a_principal() -> None:
    principal = get_principal(
        settings=_settings("dev"),
        x_user_id="usr_0001",
        x_user_email="alice@example.com",
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email == "alice@example.com"


def test_dev_with_header_but_no_email_still_resolves() -> None:
    principal = get_principal(
        settings=_settings("dev"), x_user_id="usr_0001", x_user_email=None
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email is None


def test_dev_without_header_resolves_to_none() -> None:
    assert (
        get_principal(settings=_settings("dev"), x_user_id=None, x_user_email=None)
        is None
    )


def test_non_dev_ignores_the_header_even_when_present() -> None:
    # The trust-boundary relaxation is dev-only: staging/prod must fail closed
    # until real JWT verification replaces this stub.
    principal = get_principal(
        settings=_settings("staging"),
        x_user_id="usr_0001",
        x_user_email="alice@example.com",
    )

    assert principal is None
