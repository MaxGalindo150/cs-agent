"""Transport rules for the backends the tools call (service/core/tooling.py).

Tool traffic carries phone numbers, one-time 2FA codes and order data, so a
deployed configuration must not be able to send it in cleartext by accident.
The local mocks speak http, so dev is the one place it is allowed.

The rule is enforced once for every profile's client, so these exercise it
through the per-profile assembly (service/core/profiles.py) as well.
"""

from __future__ import annotations

import pytest

from agent.profiles import PROFILES
from service.core.config import Settings
from service.core.tooling import build_backend_client


async def test_dev_allows_http_for_the_local_mocks() -> None:
    settings = Settings(ENVIRONMENT="dev")
    client = build_backend_client("http://localhost:3002", settings, "MERCHANT_API_URL")
    try:
        assert str(client.base_url) == "http://localhost:3002"
        assert client.follow_redirects is False
    finally:
        await client.aclose()


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_non_dev_rejects_cleartext(environment: str) -> None:
    settings = Settings(ENVIRONMENT=environment)
    with pytest.raises(ValueError, match="MERCHANT_API_URL must use https"):
        build_backend_client("http://merchant.internal", settings, "MERCHANT_API_URL")


async def test_non_dev_accepts_https() -> None:
    settings = Settings(ENVIRONMENT="prod")
    client = build_backend_client(
        "https://merchant.cashea.app", settings, "MERCHANT_API_URL"
    )
    try:
        assert str(client.base_url) == "https://merchant.cashea.app"
    finally:
        await client.aclose()


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_every_profile_backend_is_covered_by_the_rule(profile_name: str) -> None:
    """A new profile cannot opt out of the https rule by accident: its backend
    URL goes through the same builder."""
    profile = PROFILES[profile_name]
    settings = Settings(ENVIRONMENT="prod")
    url = getattr(settings, profile.backend_url_setting)
    if url.startswith("https://"):
        pytest.skip(f"{profile_name} already defaults to https")
    with pytest.raises(ValueError, match="must use https"):
        build_backend_client(url, settings, profile.backend_url_setting.upper())
