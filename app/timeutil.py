"""
Time-zone aware "now" for analytics boundaries. The user's IANA zone arrives in the
internal JWT; the server clock's zone must never decide what "today" is.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def _utcnow() -> datetime:
    """Current instant in UTC (tests replace this)."""
    return datetime.now(UTC)


def local_now(tz: str) -> datetime:
    """Current wall-clock time in the given IANA zone."""
    return _utcnow().astimezone(ZoneInfo(tz))


def local_today(tz: str) -> date:
    """Today's calendar date in the given IANA zone."""
    return local_now(tz).date()
