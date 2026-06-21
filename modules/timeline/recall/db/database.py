"""Engine/session management for the SQLite database.

Uses WAL mode for concurrent read (UI) + write (tracker) access, and a
single shared engine per process. Sessions are created via a factory.
"""
from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import DB_PATH
from ..logging_setup import get_logger
from .migrations import run_migrations

log = get_logger("db.database")


def _configure_sqlite(dbapi_con, _record) -> None:
    """Apply pragmas for durability + concurrency on every connection."""
    cur = dbapi_con.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            f"sqlite:///{path}",
            future=True,
            # check_same_thread off: we manage sessions per-use and use WAL.
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _configure_sqlite)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )
        run_migrations(self.engine)
        log.info("Database ready at %s", path)

    def session(self) -> Session:
        return self._session_factory()


_lock = threading.Lock()
_instance: Database | None = None


def get_database() -> Database:
    global _instance
    with _lock:
        if _instance is None:
            _instance = Database()
        return _instance
