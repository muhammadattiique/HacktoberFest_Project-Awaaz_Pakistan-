"""
Timezone helpers for Awaaz Pakistan.

All timestamps are persisted as *naive UTC* datetimes so that the SQLite
backend stores a single unambiguous representation and existing rows remain
comparable. ``datetime.utcnow()`` is deprecated since Python 3.12 and will be
removed, so every call site goes through :func:`utcnow` instead.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_naive_utc(value: datetime) -> datetime:
    """Normalise a datetime to naive UTC (tolerant of aware inputs)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
