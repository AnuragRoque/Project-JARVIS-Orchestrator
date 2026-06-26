"""Query parsing: turn a natural search string into a structured SearchQuery.

Handles inline time expressions ("yesterday", "today", "last week", "this
month") and simple field filters, leaving the remaining words as free text for
full-text matching.

Examples
--------
    "react native audio yesterday"
        -> text="react native audio", since/until = yesterday's bounds
    "resume.pdf type:pdf"
        -> text="resume.pdf", file_type="pdf"
    "docs domain:developer.android.com today"
        -> text="docs", domain="developer.android.com", since=today
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class SearchQuery:
    text: str = ""
    since: datetime | None = None
    until: datetime | None = None
    kinds: list[str] = field(default_factory=list)   # session/browser/file
    file_type: str | None = None
    domain: str | None = None
    app: str | None = None
    limit: int = 100

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


def _day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()  # local tz for "today"


# Map coarse "kind" words the user might type to our record kinds.
_KIND_WORDS = {
    "app": "session", "apps": "session", "application": "session",
    "window": "session", "windows": "session",
    "browser": "browser", "web": "browser", "site": "browser",
    "page": "browser", "tab": "browser",
    "file": "file", "files": "file", "document": "file", "doc": "file",
}


def parse_query(raw: str) -> SearchQuery:
    q = SearchQuery()
    if not raw:
        return q
    text = raw.strip()
    now = _now()

    # --- explicit field:value filters ---
    def take_field(name: str) -> str | None:
        nonlocal text
        m = re.search(rf"\b{name}:(\S+)", text, re.IGNORECASE)
        if m:
            text = (text[:m.start()] + text[m.end():]).strip()
            return m.group(1)
        return None

    q.file_type = take_field("type") or take_field("ext")
    q.domain = take_field("domain") or take_field("site")
    q.app = take_field("app")
    kind_val = take_field("kind")
    if kind_val:
        mapped = _KIND_WORDS.get(kind_val.lower())
        if mapped:
            q.kinds.append(mapped)

    # --- time expressions ---
    lowered = text.lower()

    def strip_phrase(phrase: str) -> None:
        nonlocal text, lowered
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE).strip()
        lowered = text.lower()

    if "yesterday" in lowered:
        start, end = _day_bounds(now - timedelta(days=1))
        q.since, q.until = start, end
        strip_phrase("yesterday")
    elif "today" in lowered:
        start, end = _day_bounds(now)
        q.since, q.until = start, end
        strip_phrase("today")
    elif "last week" in lowered:
        q.since = now - timedelta(days=7)
        strip_phrase("last week")
    elif "this week" in lowered:
        q.since = now - timedelta(days=now.weekday())
        strip_phrase("this week")
    elif "last month" in lowered:
        q.since = now - timedelta(days=30)
        strip_phrase("last month")
    elif "this month" in lowered:
        q.since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        strip_phrase("this month")

    # --- bare kind words ("chrome files today") ---
    remaining = []
    for word in text.split():
        mapped = _KIND_WORDS.get(word.lower())
        if mapped and mapped not in q.kinds:
            q.kinds.append(mapped)
        else:
            remaining.append(word)
    # Only strip kind words if they were clearly filters (keep text if that
    # would empty an otherwise meaningful query).
    if remaining or q.kinds:
        # Keep original words too when they might be part of the search intent
        # (e.g. "chrome" is both a kind hint and a useful search term). We do
        # NOT drop them from text — kinds act as an *additional* filter only
        # when the user typed an explicit kind: filter. So restore full text.
        pass
    q.text = text.strip()

    # Normalise datetimes to naive-local -> aware is fine; DB stores UTC-naive
    # via utcnow(). Convert bounds to UTC-naive for comparison consistency.
    q.since = _to_db(q.since)
    q.until = _to_db(q.until)
    return q


def _to_db(dt: datetime | None) -> datetime | None:
    """Convert an aware local datetime to the naive UTC form the DB stores."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
