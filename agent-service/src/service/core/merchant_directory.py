"""Who a verified host user is at Cashea, when they're an aliado.

merchant-web's Firebase tokens carry no merchant claims; the portal learns an
employee's merchant, store and role from ``GET /employees/{uid}`` on Cashea's
merchant API, sent with the employee's own token. ``POST /v1/auth/session``
does the same, once per session token, so the merchant fields on a
``Principal`` come from Cashea's backend — never from the caller.

Any failure (not an employee, backend down, unexpected shape) means "not a
merchant": the caller still gets a session, as a consumer. It never blocks
sign-in, and it never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class MerchantEmployee:
    merchant_id: str
    merchant_name: str | None
    store_id: str | None
    store_uuid: str | None
    store_name: str | None
    role: str | None


async def lookup_employee(
    client: httpx.AsyncClient, uid: str, host_token: str
) -> MerchantEmployee | None:
    """The aliado record for ``uid``, or None if they aren't one (or we can't
    tell right now). ``client`` is based at MERCHANT_API_URL."""
    try:
        resp = await client.get(
            f"/employees/{uid}", headers={"Authorization": f"Bearer {host_token}"}
        )
    except httpx.HTTPError as exc:
        log.warning("merchant_directory.unreachable", error=type(exc).__name__)
        return None
    if resp.status_code != 200:
        log.info("merchant_directory.not_found", status=resp.status_code)
        return None
    try:
        return _to_employee(resp.json())
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("merchant_directory.bad_response", error=type(exc).__name__)
        return None


def _to_employee(data: dict[str, Any]) -> MerchantEmployee | None:
    merchant_id = data.get("merchantId")
    if merchant_id is None:
        return None
    store = data.get("store") or {}
    merchant = data.get("merchant") or {}
    return MerchantEmployee(
        merchant_id=str(merchant_id),
        merchant_name=merchant.get("name"),
        store_id=_optional_str(store.get("id")),
        store_uuid=store.get("uuid"),
        store_name=store.get("name"),
        role=data.get("role"),
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
