"""Pure, testable time helpers.

Two timestamp conventions live in a Samsung Health export:

1. CSV string columns (``start_time``, ``end_time``, ``create_time`` ...):
   a wall-clock string like ``2025-01-08 21:00:00.000`` that is stored in
   **UTC**, paired with a separate ``time_offset`` column like ``UTC+0400``.
   This was verified empirically against the epoch-ms in the binning JSON:
   the CSV string equals the UTC rendering of the same event, so the local
   time the user actually experienced is ``UTC string + offset``.

2. Epoch milliseconds inside the binning JSON files (``start_time`` ints),
   which are plain Unix-ms in UTC.

Daily-summary tables use a ``day_time`` string (local midnight, e.g.
``2025-01-10 00:00:00.000``) with no offset column; its date part is taken
as the local calendar day directly.

Everything here is a pure function of its inputs (no clock reads), so it is
trivially unit-testable and safe to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

_UTC = timezone.utc


def parse_offset(offset_str: str | None) -> timezone | None:
    """``"UTC+0400"`` -> ``timezone(+4h)``. Returns None if unparseable/empty."""
    if not offset_str:
        return None
    s = offset_str.strip()
    if not s.upper().startswith("UTC") or len(s) < 8:
        return None
    sign = 1 if s[3] == "+" else -1
    try:
        hours = int(s[4:6])
        minutes = int(s[6:8])
    except ValueError:
        return None
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def parse_utc_string(s: str) -> datetime | None:
    """Parse a Samsung CSV wall-clock string (which is in UTC) to an aware UTC datetime."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=_UTC)
        except ValueError:
            continue
    return None


def _to_offset(dt_utc: datetime, offset_str: str | None) -> datetime:
    tz = parse_offset(offset_str) or _UTC
    return dt_utc.astimezone(tz)


def utc_string_to_iso(s: str, offset_str: str | None) -> str | None:
    """CSV UTC string + offset -> local ISO-8601 like ``2025-01-09T01:00:00+04:00``."""
    dt = parse_utc_string(s)
    if dt is None:
        return None
    return _to_offset(dt, offset_str).replace(microsecond=0).isoformat()


def utc_string_to_local_date(s: str, offset_str: str | None) -> date | None:
    """Local calendar date the record belongs to (UTC string shifted by offset)."""
    dt = parse_utc_string(s)
    if dt is None:
        return None
    return _to_offset(dt, offset_str).date()


def epoch_ms_to_iso(ms: int, offset_str: str | None) -> str | None:
    """Epoch-ms (UTC) -> local ISO-8601 in the given offset."""
    if ms is None:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=_UTC)
    return _to_offset(dt, offset_str).replace(microsecond=0).isoformat()


def epoch_ms_to_local_date(ms: int, offset_str: str | None) -> date | None:
    if ms is None:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=_UTC)
    return _to_offset(dt, offset_str).date()


def parse_day_time(s: str) -> date | None:
    """``day_time`` string (local midnight) -> its calendar date."""
    dt = parse_utc_string(s)  # same textual format; we only keep the date part
    return dt.date() if dt else None


def timecode_to_date(timecode: str) -> date | None:
    """Export folder timecode (``20260722105897``) -> its date (first 8 digits)."""
    if not timecode or len(timecode) < 8 or not timecode[:8].isdigit():
        return None
    try:
        return datetime.strptime(timecode[:8], "%Y%m%d").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class Window:
    """Inclusive local-date window ``[start_date, end_date]``."""

    start_date: date
    end_date: date

    @classmethod
    def last_n_days(cls, anchor: date, n_days: int) -> "Window":
        # "last N days" including the anchor day itself
        n = max(1, n_days)
        return cls(anchor - timedelta(days=n - 1), anchor)

    def contains(self, d: date | None) -> bool:
        return d is not None and self.start_date <= d <= self.end_date

    def as_dict(self, n_days: int, primary_offset: str | None) -> dict:
        return {
            "n_days": n_days,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "primary_utc_offset": primary_offset or "UTC+0000",
        }
