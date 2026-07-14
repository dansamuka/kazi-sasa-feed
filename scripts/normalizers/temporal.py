"""Defensive date/time normalisation for third-party job feeds.

Public job APIs use a mix of ISO-8601, SQL-style UTC timestamps, date-only
values and epoch timestamps.  The public feed contract requires timezone-aware
ISO-8601 strings, so collectors route temporal values through this module.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import Any

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")


def _as_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    # Keep second precision for deterministic output and broad client support.
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalise_datetime(value: Any, *, end_of_day: bool = False) -> str | None:
    """Return a timezone-aware ISO-8601 UTC string or ``None``.

    Supported inputs include:
    - ``2026-07-06T07:30:06Z``
    - ``2026-07-06 07:30:06 UTC`` (Recruitee live format)
    - ``2026-07-06``
    - Unix seconds or milliseconds
    - RFC-2822/HTTP-date strings
    """
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return _as_utc_z(value)
    if isinstance(value, date):
        chosen = time(23, 59, 59) if end_of_day else time(0, 0, 0)
        return _as_utc_z(datetime.combine(value, chosen, tzinfo=timezone.utc))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        # Millisecond epochs are currently ~1e12; seconds are ~1e9.
        if abs(number) > 10_000_000_000:
            number /= 1000.0
        try:
            return _as_utc_z(datetime.fromtimestamp(number, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if _NUMERIC.fullmatch(text):
        try:
            return normalise_datetime(float(text), end_of_day=end_of_day)
        except ValueError:
            return None

    if _DATE_ONLY.fullmatch(text):
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError:
            return None
        chosen = time(23, 59, 59) if end_of_day else time(0, 0, 0)
        return _as_utc_z(datetime.combine(parsed_date, chosen, tzinfo=timezone.utc))

    # Normalise common source variants before using the stdlib ISO parser.
    candidate = text
    candidate = re.sub(r"\s+(UTC|GMT)$", "+00:00", candidate, flags=re.I)
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return _as_utc_z(datetime.fromisoformat(candidate))
    except ValueError:
        pass

    try:
        return _as_utc_z(parsedate_to_datetime(text))
    except (TypeError, ValueError, OverflowError):
        return None


def normalise_opportunity_temporal_fields(opportunity: dict) -> dict:
    """Normalise temporal fields and discard impossible closing dates.

    A stale or unrelated date inside a description must not invalidate the
    entire feed.  Where a parsed deadline predates the posting timestamp, the
    deadline is removed and its confidence reset to ``unknown``.  The job is
    retained because the source posting itself may still be current.
    """
    posted = normalise_datetime(opportunity.get("posted_at"), end_of_day=False)
    deadline = normalise_datetime(opportunity.get("deadline"), end_of_day=True)

    opportunity["posted_at"] = posted
    opportunity["deadline"] = deadline

    if posted and deadline:
        posted_dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
        deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if deadline_dt < posted_dt:
            opportunity["deadline"] = None
            opportunity["deadline_confidence"] = "unknown"
            quality = opportunity.setdefault("data_quality", {})
            quality["deadline_dropped"] = "before_posted_at"

    if opportunity.get("deadline") is None:
        opportunity["deadline_confidence"] = "unknown"

    return opportunity
