"""Time helpers. Always work in UTC."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware (assumes naive == UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
