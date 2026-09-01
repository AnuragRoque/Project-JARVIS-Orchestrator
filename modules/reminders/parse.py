"""Turn free-text time expressions into a concrete datetime.

Prefers ``dateparser`` (handles "tomorrow at 9", "next monday 6pm", "in 2 hours",
"june 5 3pm", …). Falls back to a small built-in parser for the common relative
and clock forms if dateparser is unavailable, so the feature degrades gracefully.

Always returns a **local-naive** ``datetime`` in the future (or ``None``).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

try:
    import dateparser
    _HAS_DATEPARSER = True
except Exception:  # pragma: no cover
    _HAS_DATEPARSER = False

_UNIT_SECONDS = {
    "second": 1, "sec": 1, "s": 1,
    "minute": 60, "min": 60, "m": 60,
    "hour": 3600, "hr": 3600, "h": 3600,
    "day": 86400, "d": 86400,
    "week": 604800, "wk": 604800, "w": 604800,
}


def parse_when(text: str, base: datetime | None = None) -> datetime | None:
    base = base or datetime.now()
    text = (text or "").strip()
    if not text:
        return None

    # 1) fast path: "in 2 minutes", "in 30 sec", "after 1 hour", "2h", …
    dt = _relative(text, base)
    if dt:
        return dt

    # 2) dateparser (rich)
    if _HAS_DATEPARSER:
        try:
            dt = dateparser.parse(text, settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": False,
                "RELATIVE_BASE": base,
            })
        except Exception:
            dt = None
        if dt:
            # If it landed in the past (e.g. bare "6pm" already passed), bump a day.
            if dt <= base:
                dt = dt + timedelta(days=1)
            return dt

    # 3) fallback clock parser ("at 6pm", "tomorrow 9:30 am")
    return _clock(text, base)


def _relative(text: str, base: datetime) -> datetime | None:
    m = re.search(
        r"\b(?:in|after)?\s*(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|"
        r"days?|weeks?|wks?|[smhdw])\b", text, re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower().rstrip("s")
    secs = _UNIT_SECONDS.get(unit)
    if not secs:
        return None
    return base + timedelta(seconds=n * secs)


_CLOCK_RE = re.compile(
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)?", re.IGNORECASE)


def _clock(text: str, base: datetime) -> datetime | None:
    low = text.lower()
    day = base
    if "tomorrow" in low:
        day = base + timedelta(days=1)
    m = _CLOCK_RE.search(low)
    if not m:
        return None
    hour = int(m.group("h"))
    minute = int(m.group("m") or 0)
    ap = m.group("ap")
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    dt = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if dt <= base and "tomorrow" not in low:
        dt += timedelta(days=1)
    return dt
