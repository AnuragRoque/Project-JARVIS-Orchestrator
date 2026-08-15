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

_ensured = False


def _ensure(cur) -> None:
    cur.execute(
        "CREATE TABLE IF NOT EXISTS event_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, module TEXT, "
        "summary TEXT, detail TEXT, risk TEXT, decision TEXT)"
    )


def log_event(kind: str, summary: str, *, module: str = "", detail: str = "",
              risk: str = "", decision: str = "") -> None:
    """Append one row and publish it on the bus for live subscribers."""
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
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
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            rows = cur.execute(
                "SELECT ts, kind, module, summary, detail, risk, decision "
                "FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        log.debug("event_log read failed", exc_info=True)
        return []
