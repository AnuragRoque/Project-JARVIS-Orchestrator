"""Timeline module: recall + reopen the user's own past activity.

Exposes recall_search / recall_open / list_recent_files / browser_recall to the
orchestrator. Search results are cached so a follow-up like "open the third one"
resolves by index or ref. (browser_recall lives here in Phase 2 since it shares
the same store; it splits into its own module in Phase 5.)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool
from jarvis.modules.timeline.recall.resource import OpenError, open_result
from jarvis.modules.timeline.recall.search import get_search_engine
from jarvis.modules.timeline.recall.storage import get_repository

log = get_logger("module.timeline")


# ------------------------------------------------------------------ specs
def _since_desc() -> str:
    return ("Optional time window, e.g. 'today', 'yesterday', 'last 2 days', "
            "'last week'. Omit for all time.")


RECALL_SEARCH_SPEC = {
    "type": "function",
    "function": {
        "name": "recall_search",
        "description": (
            "Search the user's OWN past activity — apps/windows used, browser pages "
            "viewed, and files opened — by keywords and time. Use for 'what was I "
            "doing', 'documents I opened about X', 'find the page I was reading'. "
            "Returns numbered matches; reopen one with recall_open."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for."},
                "since": {"type": "string", "description": _since_desc()},
                "kind": {"type": "string", "enum": ["session", "browser", "file"],
                          "description": "Optional: restrict to apps, browser, or files."},
                "limit": {"type": "integer", "description": "Max results (default 15)."},
            },
            "required": ["query"],
        },
    },
}

RECALL_OPEN_SPEC = {
    "type": "function",
    "function": {
        "name": "recall_open",
        "description": (
            "Reopen an item from the most recent recall_search / list_recent_files / "
            "browser_recall results. URLs open in the browser, files in their default "
            "app, apps switch to the running window. Identify it by index (1-based) or ref."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "1-based index from the last results."},
                "ref": {"type": "string", "description": "The 'ref' token of a specific result."},
            },
        },
    },
}

LIST_RECENT_FILES_SPEC = {
    "type": "function",
    "function": {
        "name": "list_recent_files",
        "description": "List the user's most recently used files, optionally within a time window.",
        "parameters": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": _since_desc()},
                "limit": {"type": "integer", "description": "Max results (default 15)."},
            },
        },
    },
}

ACTIVITY_SUMMARY_SPEC = {
    "type": "function",
    "function": {
        "name": "activity_summary",
        "description": (
            "Summarise how the user spent time on this PC over a period: total "
            "active time (hours), which apps/sites they used most, and when they "
            "started/stopped. Use this for 'how many hours did I work/use the "
            "laptop', 'how long was I on VS Code', 'what did I do yesterday', "
            "'how productive was I today'. Computed from the activity timeline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": _since_desc()},
                "query": {"type": "string", "description":
                          "Optional: focus on one app/site, e.g. 'vs code', 'chrome'."},
            },
        },
    },
}

BROWSER_RECALL_SPEC = {
    "type": "function",
    "function": {
        "name": "browser_recall",
        "description": (
            "Search the user's browser history (pages they viewed), newest first. Use "
            "for 'the video I was watching', 'that article', 'the Hotstar tab'. Pair "
            "with recall_open to reopen the page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords (site, title, topic)."},
                "since": {"type": "string", "description": _since_desc()},
                "limit": {"type": "integer", "description": "Max results (default 15)."},
            },
            "required": ["query"],
        },
    },
}


class TimelineModule(Module):
    id = "timeline"
    name = "Activity Timeline"
    version = "0.1.0"

    def __init__(self) -> None:
        self.search = None
        self.repo = None
        self._by_ref: dict[str, dict] = {}
        self._order: list[str] = []

    def start(self, ctx: AppContext) -> None:
        self.search = get_search_engine()
        self.repo = get_repository()

    def tools(self) -> list[Tool]:
        return [
            Tool(RECALL_SEARCH_SPEC, self.recall_search, "read_only"),
            Tool(RECALL_OPEN_SPEC, self.recall_open, "safe_action"),
            Tool(LIST_RECENT_FILES_SPEC, self.list_recent_files, "read_only"),
            Tool(BROWSER_RECALL_SPEC, self.browser_recall, "read_only"),
            Tool(ACTIVITY_SUMMARY_SPEC, self.activity_summary, "read_only"),
        ]

    # ----------------------------------------------------------- handlers
    def recall_search(self, query: str = "", since: str | None = None,
                      kind: str | None = None, limit: int = 15) -> dict:
        if (query or "").strip():
            results = self.search.search(query)
        else:
            # No keyword ('recall yesterday', 'what did I do today') — fall back to
            # recent activity in the window rather than returning nothing.
            results = self._recent_all(kind)
        results = self._filter(results, since=since, kind=kind)
        return self._cache_and_format(results[:_lim(limit)], query=query or "recent activity")

    def _recent_all(self, kind: str | None) -> list[dict]:
        """Recent items across the timeline (no text query), for broad recalls."""
        out: list[dict] = []
        if kind in (None, "session"):
            out += self.repo.recent_sessions(limit=300)
        if kind in (None, "browser"):
            out += self.repo.recent_browser_visits(limit=200)
        if kind in (None, "file"):
            out += self.repo.recent_files(limit=200)
        return out

    def activity_summary(self, since: str | None = None,
                         query: str = "") -> dict:
        """Aggregate active time + top apps for a window (answers 'how many hours')."""
        cutoff = _parse_since(since)
        sessions = self.repo.recent_sessions(since=cutoff, limit=5000)
        terms = [t for t in (query or "").lower().split() if t]
        if terms:
            def _hit(s: dict) -> bool:
                hay = f"{s.get('app','')} {s.get('title','')} {s.get('process_name','')}".lower()
                return all(t in hay for t in terms)
            sessions = [s for s in sessions if _hit(s)]
        if not sessions:
            return {"since": since or "all time", "sessions": 0,
                    "note": ("No activity was recorded for that period. This means "
                             "the timeline has no data for it — say so plainly; do "
                             "NOT claim an amount of time.")}
        total = sum(float(s.get("duration_seconds") or 0.0) for s in sessions)
        per_app: dict[str, float] = {}
        for s in sessions:
            app = s.get("app") or s.get("process_name") or "unknown"
            per_app[app] = per_app.get(app, 0.0) + float(s.get("duration_seconds") or 0.0)
        top = sorted(per_app.items(), key=lambda kv: kv[1], reverse=True)[:6]
        starts = [s.get("start_time") for s in sessions if s.get("start_time")]
        ends = [s.get("end_time") for s in sessions if s.get("end_time")]
        return {
            "since": since or "all time",
            "sessions": len(sessions),
            "active_time": _dur(total),
            "active_hours": round(total / 3600.0, 2),
            "first_active": _when(min(starts)) if starts else "",
            "last_active": _when(max(ends)) if ends else "",
            "top_apps": [{"app": a, "time": _dur(sec)} for a, sec in top],
        }

    def browser_recall(self, query: str = "", since: str | None = None,
                       limit: int = 15) -> dict:
        results = self.search.search(query) if (query or "").strip() else []
        results = self._filter(results, since=since, kind="browser")
        if not results:  # fall back to recent visits with a loose text match
            terms = [t.lower() for t in (query or "").split() if len(t) > 1]
            for v in self.repo.recent_browser_visits(limit=300):
                hay = f"{v.get('title','')} {v.get('domain','')} {v.get('url','')}".lower()
                if not terms or all(t in hay for t in terms):
                    results.append(v)
            results = self._filter(results, since=since)
        return self._cache_and_format(results[:_lim(limit)], query=query)

    def list_recent_files(self, since: str | None = None, limit: int = 15) -> dict:
        rows = self.repo.recent_files(limit=200)
        rows = self._filter(rows, since=since)
        return self._cache_and_format(rows[:_lim(limit)], query="recent files")

    def recall_open(self, index: int | None = None, ref: str | None = None) -> dict:
        item = None
        if ref and ref in self._by_ref:
            item = self._by_ref[ref]
        elif index is not None and 1 <= int(index) <= len(self._order):
            item = self._by_ref[self._order[int(index) - 1]]
        if item is None:
            return {"ok": False,
                    "error": ("No such result — the current list is empty or that "
                              "index doesn't exist. Run a fresh recall_search / "
                              "browser_recall / list_recent_files first; do NOT open "
                              "an item from an earlier list.")}
        try:
            msg = open_result(item)
            return {"ok": True, "message": msg,
                    "opened": (item.get("title") or "").strip()[:120] or _detail(item)}
        except OpenError as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------ helpers
    def _filter(self, results: list[dict], since: str | None = None,
                kind: str | None = None) -> list[dict]:
        cutoff = _parse_since(since)
        out = []
        for r in results:
            if kind and r.get("kind") != kind:
                continue
            if cutoff:
                st = r.get("start_time")
                if st is None or st < cutoff:
                    continue
            out.append(r)
        out.sort(key=lambda r: r.get("start_time") or datetime.min, reverse=True)
        return out

    def _cache_and_format(self, results: list[dict], query: str) -> dict:
        self._by_ref.clear()
        self._order.clear()
        items = []
        for i, r in enumerate(results, 1):
            ref = f"{r.get('kind')}:{r.get('id')}"
            self._by_ref[ref] = r
            self._order.append(ref)
            items.append({
                "index": i,
                "ref": ref,
                "kind": r.get("kind"),
                "title": (r.get("title") or "").strip()[:120] or "(untitled)",
                "detail": _detail(r),
                "when": _when(r.get("start_time")),
            })
        out = {"query": query, "count": len(items), "results": items}
        if not items:
            out["note"] = ("Nothing matched. Tell the user you couldn't find it; "
                           "do NOT open an item from any earlier list.")
        return out


# --------------------------------------------------------------- utilities
def _lim(limit) -> int:
    try:
        return max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return 15


def _dur(seconds: float) -> str:
    """Human duration: '3h 12m', '45m', '30s'."""
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    if m:
        return f"{m}m"
    return f"{s}s"


def _detail(r: dict) -> str:
    kind = r.get("kind")
    if kind == "browser":
        return r.get("domain") or r.get("url", "")
    if kind == "file":
        return r.get("path", "")
    return r.get("app", "") or r.get("process_name", "")


def _when(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%b %d, %I:%M %p").replace(" 0", " ")


def _parse_since(since: str | None) -> datetime | None:
    """Return a naive-UTC cutoff for a free-text window, or None."""
    if not since:
        return None
    s = since.strip().lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if s in ("today",):
        return _local_midnight_utc(0)
    if s in ("yesterday",):
        return _local_midnight_utc(1)
    if s in ("this week", "last week"):
        return now - timedelta(days=7)
    if s in ("this month", "last month"):
        return now - timedelta(days=30)

    m = re.search(r"(\d+)\s*day", s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*hour", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*week", s)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    return None


def _local_midnight_utc(days_ago: int) -> datetime:
    local_now = datetime.now().astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=days_ago)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def get_module() -> Module:
    return TimelineModule()
