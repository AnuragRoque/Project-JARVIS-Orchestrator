"""Lightweight schema versioning and migrations.

We keep a ``schema_version`` value in the SQLite ``user_version`` pragma. On
startup we create the ORM tables (idempotent) and then run any pending
migration steps to add FTS tables / structural changes. Each migration is a
callable taking a raw DBAPI connection.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..logging_setup import get_logger
from .models import Base

log = get_logger("db.migrations")

CURRENT_VERSION = 1


def _get_user_version(conn) -> int:
    return conn.exec_driver_sql("PRAGMA user_version").scalar() or 0


def _set_user_version(conn, version: int) -> None:
    conn.exec_driver_sql(f"PRAGMA user_version = {int(version)}")


def _migration_001_fts(conn) -> None:
    """Create the unified FTS5 search table and a mapping to source rows.

    ``search_fts`` is an external-content-less FTS5 table maintained by the
    repository. Columns:
        kind    - 'session' | 'browser' | 'file' | 'resource'
        ref_id  - primary key of the source row
        title   - main display text (window title / page title / filename)
        subtitle- secondary text (app name / domain / path)
        body    - extra searchable text (url, full path, etc.)
    """
    conn.exec_driver_sql(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            kind UNINDEXED,
            ref_id UNINDEXED,
            title,
            subtitle,
            body,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )


MIGRATIONS: list[Callable] = [
    _migration_001_fts,  # -> version 1
]


def run_migrations(engine: Engine) -> None:
    """Create ORM tables and apply pending migrations."""
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        version = _get_user_version(conn)
        if version >= CURRENT_VERSION:
            log.debug("Schema up to date (v%d)", version)
            return
        for i in range(version, CURRENT_VERSION):
            migration = MIGRATIONS[i]
            log.info("Applying migration -> v%d (%s)", i + 1, migration.__name__)
            migration(conn)
            _set_user_version(conn, i + 1)
        log.info("Migrations complete, schema at v%d", CURRENT_VERSION)
