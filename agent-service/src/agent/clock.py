"""Cashea's local time. Its users — customers and aliados — are in Venezuela,
fixed at UTC-4 since 2016; a fixed offset avoids depending on tzdata in the
image. The container itself runs in UTC."""

from datetime import datetime, timedelta, timezone

VENEZUELA = timezone(timedelta(hours=-4), "VET")


def now() -> datetime:
    return datetime.now(VENEZUELA)
