"""Transport rules for the backends the tools call (service/core/tooling.py).

Tool traffic carries phone numbers, one-time 2FA codes and order data, so a
deployed configuration must not be able to send it in cleartext by accident.
The local mocks speak http, so dev is the one place it is allowed.
"""

from __future__ import annotations

import pytest

from service.core.config import Settings
from service.core.tooling import build_bnpl_client, build_merchant_client


async def test_dev_allows_http_for_the_local_mocks() -> None:
    settings = Settings(ENVIRONMENT="dev", MERCHANT_API_URL="http://localhost:3002")
    client = build_merchant_client(settings)
    try:
        assert str(client.base_url) == "http://localhost:3002"
        assert client.follow_redirects is False
    finally:
        await client.aclose()


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_non_dev_rejects_cleartext_merchant_url(environment: str) -> None:
    settings = Settings(
        ENVIRONMENT=environment, MERCHANT_API_URL="http://merchant.internal"
    )
    with pytest.raises(ValueError, match="MERCHANT_API_URL must use https"):
        build_merchant_client(settings)


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_non_dev_rejects_cleartext_bnpl_url(environment: str) -> None:
    settings = Settings(ENVIRONMENT=environment, BNPL_API_URL="http://bnpl.internal")
    with pytest.raises(ValueError, match="BNPL_API_URL must use https"):
        build_bnpl_client(settings)


async def test_non_dev_accepts_https() -> None:
    settings = Settings(
        ENVIRONMENT="prod", MERCHANT_API_URL="https://merchant.cashea.app"
    )
    client = build_merchant_client(settings)
    try:
        assert str(client.base_url) == "https://merchant.cashea.app"
    finally:
        await client.aclose()
