"""Shared SQLite database for the kernel (WAL mode).

This is the app-level DB (``jarvis.db``) for cross-cutting data added in later
phases: reminders, the structured event log, and conversation history. Feature
modules that already own a database (e.g. the timeline's ``activity.db``) keep
theirs; this is additive, not a replacement.

Kept deliberately small — a raw ``sqlite3`` connection factory with WAL pragmas.
Tables are created by whoever owns them, on first use.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config.paths import DB_PATH, ensure_dirs
from ..logsetup import get_logger

log = get_logger("db")


class Database:
    """Thread-safe-ish SQLite gateway. Opens a fresh connection per ``cursor()``."""

    def __init__(self, path: Path | str | None = None) -> None:
        ensure_dirs()
        self.path = str(path or DB_PATH)
        self._lock = threading.RLock()
        # Touch the file and enable WAL so the DB exists from first boot.
        with self.cursor():
            pass
        log.info("Kernel database ready at %s", self.path)

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = sqlite3.connect(self.path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            cur = conn.cursor()
            yield cur
            conn.commit()
        finally:
            conn.close()


_db: Database | None = None
_db_lock = threading.Lock()


def get_database() -> Database:
    global _db
    with _db_lock:
        if _db is None:
            _db = Database()
        return _db
