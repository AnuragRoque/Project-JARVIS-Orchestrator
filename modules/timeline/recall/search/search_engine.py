"""Full-text keyword search over the unified FTS index, with filters.

Search flow
-----------
1. Parse the raw string into a :class:`SearchQuery` (time, filters, text).
2. If there is free text, run an FTS5 MATCH against ``search_fts`` (prefix
   matching, AND semantics, falling back to OR when AND finds nothing).
3. Hydrate the matching ``(kind, ref_id)`` rows from their source tables.
4. Apply structured filters (time range, kind, file type, domain, app).
5. Rank by a blend of FTS relevance and recency, and return unified dicts.

When there is no free text (e.g. "yesterday" only), we skip FTS and query the
source tables directly by time.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime

from sqlalchemy import select, text

from ..logging_setup import get_logger
from ..db import get_database
from ..db.models import Application, BrowserVisit, FileEvent, Session
from .query import SearchQuery, parse_query

log = get_logger("search.engine")

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def _fts_expression(text_query: str, use_or: bool) -> str:
    tokens = [t for t in _TOKEN_RE.split(text_query) if len(t) >= 2]
    if not tokens:
        # Single-char tokens: quote whole thing.
        tokens = [t for t in _TOKEN_RE.split(text_query) if t]
    if not tokens:
        return ""
    parts = [f'"{t}"*' for t in tokens]
    joiner = " OR " if use_or else " AND "
    return joiner.join(parts)


class SearchEngine:
    def __init__(self):
        self.db = get_database()
        self._lock = threading.Lock()

    def search(self, raw: str) -> list[dict]:
        q = parse_query(raw)
        if q.has_text:
            results = self._fts_search(q)
        else:
            results = self._time_search(q)
        results = self._apply_filters(results, q)
        results.sort(key=lambda r: (r.get("_score", 0.0),
                                    r.get("start_time") or datetime.min),
                     reverse=True)
        return results[: q.limit]

    # ------------------------------------------------------------------ FTS
    def _fts_search(self, q: SearchQuery) -> list[dict]:
        expr = _fts_expression(q.text, use_or=False)
        if not expr:
            return self._time_search(q)
        rows = self._run_fts(expr)
        if not rows:
            # Broaden: OR semantics for recall.
            rows = self._run_fts(_fts_expression(q.text, use_or=True))
        # rows: list of (kind, ref_id, rank)
        by_kind: dict[str, dict[int, float]] = {}
        for kind, ref_id, rank in rows:
            by_kind.setdefault(kind, {})[ref_id] = rank
        return self._hydrate(by_kind)

    def _run_fts(self, expr: str) -> list[tuple[str, int, float]]:
        if not expr:
            return []
        sql = text(
            "SELECT kind, ref_id, rank FROM search_fts "
            "WHERE search_fts MATCH :expr ORDER BY rank LIMIT 500"
        )
        with self.db.session() as orm:
            try:
                res = orm.execute(sql, {"expr": expr}).all()
            except Exception as exc:
                log.warning("FTS query failed for %r: %s", expr, exc)
                return []
        # rank is negative (better = more negative); convert to positive score.
        return [(k, int(r), -float(rk)) for k, r, rk in res]

    def _hydrate(self, by_kind: dict[str, dict[int, float]]) -> list[dict]:
        results: list[dict] = []
        with self.db.session() as orm:
            if "session" in by_kind:
                ids = list(by_kind["session"])
                rows = orm.execute(
                    select(Session, Application)
                    .join(Application, Session.application_id == Application.id)
                    .where(Session.id.in_(ids))
                ).all()
                for s, a in rows:
                    d = _session_dict(s, a)
                    d["_score"] = by_kind["session"][s.id]
                    results.append(d)
            if "browser" in by_kind:
                ids = list(by_kind["browser"])
                rows = orm.execute(
                    select(BrowserVisit).where(BrowserVisit.id.in_(ids))
                ).scalars().all()
                for v in rows:
                    d = _browser_dict(v)
                    d["_score"] = by_kind["browser"][v.id]
                    results.append(d)
            if "file" in by_kind:
                ids = list(by_kind["file"])
                rows = orm.execute(
                    select(FileEvent).where(FileEvent.id.in_(ids))
                ).scalars().all()
                for f in rows:
                    d = _file_dict(f)
                    d["_score"] = by_kind["file"][f.id]
                    results.append(d)
        return results

    # ------------------------------------------------------------- time-only
    def _time_search(self, q: SearchQuery) -> list[dict]:
        results: list[dict] = []
        with self.db.session() as orm:
            s_stmt = (
                select(Session, Application)
                .join(Application, Session.application_id == Application.id)
                .order_by(Session.start_time.desc())
                .limit(500)
            )
            if q.since:
                s_stmt = s_stmt.where(Session.start_time >= q.since)
            if q.until:
                s_stmt = s_stmt.where(Session.start_time <= q.until)
            for s, a in orm.execute(s_stmt).all():
                results.append(_session_dict(s, a))

            b_stmt = select(BrowserVisit).order_by(
                BrowserVisit.tab_activated.desc()).limit(500)
            if q.since:
                b_stmt = b_stmt.where(BrowserVisit.tab_activated >= q.since)
            if q.until:
                b_stmt = b_stmt.where(BrowserVisit.tab_activated <= q.until)
            for v in orm.execute(b_stmt).scalars().all():
                results.append(_browser_dict(v))

            f_stmt = select(FileEvent).order_by(
                FileEvent.last_activity.desc()).limit(500)
            if q.since:
                f_stmt = f_stmt.where(FileEvent.last_activity >= q.since)
            if q.until:
                f_stmt = f_stmt.where(FileEvent.last_activity <= q.until)
            for f in orm.execute(f_stmt).scalars().all():
                results.append(_file_dict(f))
        # Score by recency only.
        for r in results:
            r["_score"] = 0.0
        return results

    # -------------------------------------------------------------- filtering
    def _apply_filters(self, results: list[dict], q: SearchQuery) -> list[dict]:
        out = []
        for r in results:
            st = r.get("start_time")
            if q.since and st and st < q.since:
                continue
            if q.until and st and st > q.until:
                continue
            if q.kinds and r["kind"] not in q.kinds:
                continue
            if q.file_type and r.get("file_type", "").lower() != \
                    q.file_type.lower().lstrip("."):
                continue
            if q.domain and q.domain.lower() not in \
                    (r.get("domain", "") or "").lower():
                continue
            if q.app:
                app_hay = f"{r.get('app','')} {r.get('process_name','')}".lower()
                if q.app.lower() not in app_hay:
                    continue
            out.append(r)
        return out


def _session_dict(s: Session, a: Application) -> dict:
    return {
        "kind": "session", "id": s.id,
        "title": s.window_title or a.display_name or a.name,
        "app": a.display_name or a.name, "process_name": a.name,
        "exe_path": a.exe_path, "window_title": s.window_title,
        "start_time": s.start_time, "end_time": s.end_time,
        "duration_seconds": s.duration_seconds, "category": s.kind,
    }


def _browser_dict(v: BrowserVisit) -> dict:
    return {
        "kind": "browser", "id": v.id, "title": v.title or v.url,
        "url": v.url, "domain": v.domain, "browser": v.browser,
        "app": v.browser, "start_time": v.tab_activated,
        "duration_seconds": v.duration_seconds,
    }


def _file_dict(f: FileEvent) -> dict:
    return {
        "kind": "file", "id": f.id, "title": f.filename, "path": f.path,
        "file_type": f.file_type, "app": f.application,
        "application": f.application, "start_time": f.last_activity,
    }


_engine: SearchEngine | None = None
_engine_lock = threading.Lock()


def get_search_engine() -> SearchEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SearchEngine()
        return _engine
