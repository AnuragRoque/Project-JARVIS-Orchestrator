"""Browser module: reopen a page from the user's browsing history in one step.

Timeline's ``browser_recall`` lists matching pages so the user can pick one; this
module adds ``open_last_page`` — the direct "open the Hotstar page I was on"
shortcut that finds the newest page matching a query and reopens it immediately,
without a second round-trip. It reads the shared recall store (app-level
singletons), never a sibling module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool
from jarvis.modules.timeline.recall.resource import OpenError, open_result
from jarvis.modules.timeline.recall.search import get_search_engine
from jarvis.modules.timeline.recall.storage import get_repository

log = get_logger("module.browser")

OPEN_LAST_PAGE_SPEC = {
    "type": "function",
    "function": {
        "name": "open_last_page",
        "description": (
            "Find the most recent browser page the user viewed that matches a query "
            "and reopen it in ONE step. Use when the user clearly wants it reopened "
            "now — 'open the Hotstar page I was on', 'reopen that YouTube video', "
            "'take me back to the article about X'. For just listing pages to choose "
            "from, use browser_recall instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Site, title, or topic, e.g. 'hotstar', 'lantern'."},
                "since": {"type": "string",
                          "description": "Optional window, e.g. 'today', 'last 2 days'."},
            },
            "required": ["query"],
        },
    },
}


class BrowserModule(Module):
    id = "browser"
    name = "Browser"
    version = "0.1.0"

    def __init__(self) -> None:
        self.search = None
        self.repo = None

    def start(self, ctx: AppContext) -> None:
        self.search = get_search_engine()
        self.repo = get_repository()

    def tools(self) -> list[Tool]:
        return [Tool(OPEN_LAST_PAGE_SPEC, self.open_last_page, "safe_action")]

    # ------------------------------------------------------------- handler
    def open_last_page(self, query: str = "", since: str | None = None) -> dict:
        query = (query or "").strip()
        if not query:
            return {"ok": False, "error": "What page should I reopen?"}

        match = self._newest_match(query, since)
        if match is None:
            return {"ok": False,
                    "error": f"I couldn't find a browser page matching '{query}'."}
        try:
            open_result(match)
        except OpenError as exc:
            return {"ok": False, "error": str(exc)}
        title = (match.get("title") or match.get("url") or "").strip()[:120]
        log_event("browser", f"reopen: {title}", module="browser",
                  detail=match.get("url", ""), decision="opened")
        return {"ok": True, "opened": title, "url": match.get("url", ""),
                "message": f"Reopening {title or match.get('domain') or 'the page'}."}

    # ------------------------------------------------------------- helpers
    def _newest_match(self, query: str, since: str | None) -> dict | None:
        cutoff = _parse_since(since)
        results = [r for r in self.search.search(query)
                   if r.get("kind") == "browser"]
        if not results:  # loose text match over recent visits
            terms = [t.lower() for t in query.split() if len(t) > 1]
            for v in self.repo.recent_browser_visits(limit=500):
                hay = f"{v.get('title','')} {v.get('domain','')} {v.get('url','')}".lower()
                if not terms or all(t in hay for t in terms):
                    results.append(v)
        if cutoff:
            results = [r for r in results
                       if (r.get("start_time") is not None and r["start_time"] >= cutoff)]
        results.sort(key=lambda r: r.get("start_time") or datetime.min, reverse=True)
        return results[0] if results else None


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    import re
    s = since.strip().lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if s == "today":
        local = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    if s == "yesterday":
        local = (datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
                 - timedelta(days=1))
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    m = re.search(r"(\d+)\s*day", s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*hour", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*week", s)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    if s in ("this week", "last week"):
        return now - timedelta(days=7)
    return None


def get_module() -> Module:
    return BrowserModule()
