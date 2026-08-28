"""Structured event log → the shared SQLite DB.

Every tool execution and permission decision is appended here. It's the feed for
the future Logs tab (Phase 6) and an audit trail for what JARVIS did. Writes are
best-effort and never raise into the caller.
"""
from __future__ import annotations

from datetime import datetime

from .bus import bus
from .data.db import get_database
from .logsetup import get_logger

log = get_logger("eventlog")

_fts_ready: bool | None = None  # None = not yet probed


def _ensure(cur) -> None:
    cur.execute(
        "CREATE TABLE IF NOT EXISTS event_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, module TEXT, "
        "summary TEXT, detail TEXT, risk TEXT, decision TEXT)"
    )


def _ensure_fts(cur) -> bool:
    """Create an FTS5 mirror + sync triggers (once). Returns availability."""
    global _fts_ready
    if _fts_ready is not None:
        return _fts_ready
    try:
        cur.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS event_log_fts USING fts5("
            "summary, detail, module, kind, "
            "content='event_log', content_rowid='id')")
        cur.execute(
            "CREATE TRIGGER IF NOT EXISTS event_log_ai AFTER INSERT ON event_log "
            "BEGIN INSERT INTO event_log_fts(rowid, summary, detail, module, kind) "
            "VALUES (new.id, new.summary, new.detail, new.module, new.kind); END")
        cur.execute(
            "CREATE TRIGGER IF NOT EXISTS event_log_ad AFTER DELETE ON event_log "
            "BEGIN INSERT INTO event_log_fts(event_log_fts, rowid, summary, detail, "
            "module, kind) VALUES('delete', old.id, old.summary, old.detail, "
            "old.module, old.kind); END")
        if cur.execute("SELECT count(*) FROM event_log_fts").fetchone()[0] == 0:
            cur.execute("INSERT INTO event_log_fts(event_log_fts) VALUES('rebuild')")
        _fts_ready = True
    except Exception:
        log.debug("FTS unavailable; falling back to LIKE search", exc_info=True)
        _fts_ready = False
    return _fts_ready


def _fts_query(text: str) -> str:
    """Turn free text into a safe prefix MATCH query ('stop proc' -> 'stop* proc*')."""
    import re
    toks = [t for t in re.findall(r"[A-Za-z0-9_]+", text) if t]
    return " ".join(f"{t}*" for t in toks)


def log_event(kind: str, summary: str, *, module: str = "", detail: str = "",
              risk: str = "", decision: str = "") -> None:
    """Append one row and publish it on the bus for live subscribers."""
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            _ensure_fts(cur)  # keep the search index in sync via triggers
            cur.execute(
                "INSERT INTO event_log (ts, kind, module, summary, detail, risk, "
                "decision) VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), kind, module,
                 summary, detail, risk, decision),
            )
    except Exception:
        log.debug("event_log write skipped", exc_info=True)
    try:
        bus.publish(f"log.{kind}", {
            "kind": kind, "module": module, "summary": summary,
            "risk": risk, "decision": decision,
        })
    except Exception:
        pass


def recent_events(limit: int = 500) -> list[dict]:
    """Read back recent events (newest first) for the Logs tab."""
    return search_events(limit=limit)


def search_events(query: str = "", *, module: str | None = None,
                  decision: str | None = None, limit: int = 500) -> list[dict]:
    """Filtered + full-text search over the event log (newest first).

    ``query`` full-text-matches summary/detail/module (FTS5, or LIKE fallback);
    ``module`` / ``decision`` narrow by exact/prefix value.
    """
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            q = (query or "").strip()
            where, params, join = [], [], ""

            if q and _ensure_fts(cur) and _fts_query(q):
                join = " JOIN event_log_fts f ON f.rowid = e.id"
                where.append("event_log_fts MATCH ?")
                params.append(_fts_query(q))
            elif q:
                where.append("(e.summary LIKE ? OR e.detail LIKE ? OR e.module LIKE ?)")
                like = f"%{q}%"
                params += [like, like, like]

            if module:
                where.append("e.module = ?")
                params.append(module)
            if decision:
                where.append("e.decision LIKE ?")
                params.append(f"{decision}%")

            sql = ("SELECT e.ts, e.kind, e.module, e.summary, e.detail, e.risk, "
                   "e.decision FROM event_log e" + join)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY e.id DESC LIMIT ?"
            params.append(limit)
            rows = cur.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        log.debug("event_log search failed", exc_info=True)
        return []


def distinct_modules() -> list[str]:
    """Modules that appear in the log (for the Logs-tab filter dropdown)."""
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            rows = cur.execute(
                "SELECT DISTINCT module FROM event_log "
                "WHERE module <> '' ORDER BY module").fetchall()
        return [r["module"] for r in rows]
    except Exception:
        return []
