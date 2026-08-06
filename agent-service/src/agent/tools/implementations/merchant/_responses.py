"""Shared guards for the merchant tools.

Two things every merchant tool needs and must not get wrong twice:

* **Decoding.** An upstream 200 can still carry HTML (a proxy error page) or a
  JSON array. Calling ``.json()`` raises ``JSONDecodeError`` there, and a list
  makes the following ``.get(...)`` raise ``AttributeError``. Both surface to
  the model as a generic ``Error running <tool>`` string instead of something it
  can act on, so decoding goes through :func:`decode_object`.

* **Path segments.** ``httpx`` resolves dot segments per RFC 3986 before the
  request leaves, so an LLM-supplied ``..`` inside an f-string path escapes the
  merchant-scoped prefix (``/merchants/1/monthly-reports/../../merchants/2``
  reaches merchant 2). Anything interpolated into a path is validated here
  first — never trusted because the input schema documents a format.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

# YYYY-MM, months 01-12. The period is the only free-form value that reaches a
# path with no ownership check behind it.
_PERIOD_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")

# Ids the mock issues: digits, letters, dashes and underscores. Deliberately
# narrower than the upstream format so a traversal attempt never gets built.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def decode_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return the body as a JSON object, or ``None`` if it is not one."""
    try:
        body = response.json()
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) else None


def is_period(value: str) -> bool:
    """True when ``value`` is a ``YYYY-MM`` period safe to put in a path."""
    return bool(_PERIOD_RE.match(value))


def is_path_id(value: str) -> bool:
    """True when ``value`` is safe to interpolate as a single path segment."""
    return bool(_ID_RE.match(value))
