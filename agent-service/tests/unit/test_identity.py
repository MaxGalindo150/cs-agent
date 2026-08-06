"""Unit tests for the identity seam stub (service/core/identity.py).

STUB behavior under test: trust the identity headers verbatim, but only in dev
— everywhere else, resolve to no Principal regardless of what the caller sent.
See the module docstring for why.

Which headers a profile reads is tested in test_profiles.py; here the subject is
the trust decision and the profile dispatch.
"""

from __future__ import annotations

from typing import Any

from starlette.datastructures import Headers

from service.core.config import Settings
from service.core.identity import get_principal


def _settings(environment: str) -> Settings:
    # Settings' fields are alias-only (no populate_by_name) — ENVIRONMENT is
    # the wire name, not the Python attribute (see service/core/config.py).
    return Settings(ENVIRONMENT=environment)


def _request(**headers: str) -> Any:
    """The seam only reads `request.headers`, so a stub with that one attribute
    keeps these tests free of a full ASGI scope."""

    class _Request:
        def __init__(self, values: dict[str, str]) -> None:
            self.headers = Headers(values)

    return _Request(headers)


def test_dev_with_header_resolves_a_principal() -> None:
    principal = get_principal(
        _request(**{"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"}),
        settings=_settings("dev"),
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email == "alice@example.com"


def test_dev_with_header_but_no_email_still_resolves() -> None:
    principal = get_principal(
        _request(**{"X-User-Id": "usr_0001"}), settings=_settings("dev")
    )

    assert principal is not None
    assert principal.user_id == "usr_0001"
    assert principal.email is None


def test_dev_without_header_resolves_to_none() -> None:
    assert get_principal(_request(), settings=_settings("dev")) is None


def test_merchant_profile_header_selects_the_merchant_reader() -> None:
    principal = get_principal(
        _request(**{"X-Agent-Profile": "merchant", "X-Merchant-Id": "1"}),
        settings=_settings("dev"),
    )

    assert principal is not None
    assert principal.profile == "merchant"
    assert principal.merchant_id == "1"


def test_non_dev_ignores_the_header_even_when_present() -> None:
    # The trust-boundary relaxation is dev-only: staging/prod must fail closed
    # until real JWT verification replaces this stub.
    principal = get_principal(
        _request(**{"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"}),
        settings=_settings("staging"),
    )

    assert principal is None


def test_non_dev_ignores_merchant_headers_too() -> None:
    principal = get_principal(
        _request(**{"X-Agent-Profile": "merchant", "X-Merchant-Id": "1"}),
        settings=_settings("prod"),
    )

    assert principal is None


def test_environment_defaults_to_a_non_dev_value() -> None:
    """Fail-closed by construction: a deployment that omits ENVIRONMENT must
    not silently trust X-User-Id (or expose /docs) as if it were dev."""
    assert Settings.model_fields["environment"].default != "dev"
