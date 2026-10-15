"""Cashea's local time. Its users — customers and aliados — are in Venezuela,
fixed at UTC-4 since 2016; a fixed offset avoids depending on tzdata in the
image. The container itself runs in UTC."""

from datetime import datetime, timedelta, timezone

VENEZUELA = timezone(timedelta(hours=-4), "VET")


def now() -> datetime:
    return datetime.now(VENEZUELA)


def local(value: object) -> datetime | None:
    """An API timestamp (ISO 8601 with an offset, e.g. ``...Z``) in
    Venezuelan time; None when it isn't one."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(VENEZUELA) if moment.tzinfo else None


def describe(value: object) -> object:
    """An API timestamp as the aliado reads it; anything else unchanged."""
    moment = local(value)
    return f"{moment:%Y-%m-%d %H:%M} (hora de Venezuela)" if moment else value
