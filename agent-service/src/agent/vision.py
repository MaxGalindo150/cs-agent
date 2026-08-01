"""Image — a piece of visual context attached to one turn.

Provider- and transport-neutral (CLAUDE.md §4), mirroring ``agent/identity.py``:
lives under ``agent/`` because ``agent/app.py`` needs to name it when building
the LLM message; the wire shape it's decoded *from* (a JSON body's base64
field) is entirely a ``service/`` concern. Anthropic's four accepted media
types are enumerated here, not left as a bare ``str`` — an unsupported type
must fail at the ``service/`` boundary (pydantic validation), never surface as
an opaque 400 from the provider mid-turn.

Deliberately just this: no filename, no caption, no persistence — an image is
context for the turn it arrives in, not a durable record (see
``agent/app.py::Agent.respond`` for why the raw bytes are never written to
Postgres or replayed into later turns). A future OCR/business-validation flow
(CLAUDE.md §1) is a different consumer of a *raw* image and may need more than
this; this type only serves "let the model see it."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]


@dataclass(frozen=True, slots=True)
class Image:
    media_type: MediaType
    data: str
    """Base64-encoded bytes, undecoded — passed straight through to the
    provider's image content block. Decoded only where it must be (the
    service boundary's size validation), never held as raw bytes here."""
