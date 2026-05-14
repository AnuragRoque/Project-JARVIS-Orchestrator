from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.core.logging import logger


class DatabaseManager:
    """Manages SQLite database connections with WAL mode and automatic cleanup."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = str(db_path or settings.db_path)
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_prompt TEXT NOT NULL,
                    normalized_prompt TEXT,
                    prompt_pattern TEXT NOT NULL,
                    command_template TEXT NOT NULL,
                    param_count INTEGER DEFAULT 0,
                    risk_category TEXT DEFAULT 'READ_ONLY',
                    risk_level TEXT DEFAULT 'SAFE',
                    use_count INTEGER DEFAULT 1,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_pattern ON saved_commands(prompt_pattern);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_use_count ON saved_commands(use_count DESC);")

            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(saved_commands);")
            existing_cols = {row["name"] for row in cursor.fetchall()}

            migrations = [
                ("normalized_prompt", "TEXT"),
                ("risk_category", "TEXT DEFAULT 'READ_ONLY'"),
                ("risk_level", "TEXT DEFAULT 'SAFE'"),
                ("success_count", "INTEGER DEFAULT 1"),
                ("failure_count", "INTEGER DEFAULT 0"),
            ]

            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    logger.info(f"Migrating database: Adding column '{col_name}' to saved_commands")
                    conn.execute(f"ALTER TABLE saved_commands ADD COLUMN {col_name} {col_type};")

            conn.commit()
