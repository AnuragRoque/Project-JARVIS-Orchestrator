"""SQLite storage for reminders (in the shared kernel DB).

Times are stored as local-naive ISO strings and compared against
``datetime.now()`` — consistent because the parser also returns local-naive.
"""
from __future__ import annotations

from datetime import datetime

from jarvis.app.data.db import get_database
from jarvis.app.logsetup import get_logger

log = get_logger("reminders.store")


class ReminderStore:
    def __init__(self) -> None:
        self.db = get_database()
        with self.db.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS reminders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                "fire_at TEXT NOT NULL, created_at TEXT, status TEXT DEFAULT 'pending', "
                "recurrence TEXT, source TEXT DEFAULT 'user')"
            )

    def add(self, text: str, fire_at: datetime, recurrence: str | None = None,
            source: str = "user") -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (text, fire_at, created_at, status, "
                "recurrence, source) VALUES (?,?,?,'pending',?,?)",
                (text, fire_at.isoformat(timespec="seconds"),
                 datetime.now().isoformat(timespec="seconds"), recurrence, source),
            )
            return int(cur.lastrowid)

    def pending(self) -> list[dict]:
        with self.db.cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM reminders WHERE status='pending' ORDER BY fire_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def due(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now()
        with self.db.cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM reminders WHERE status='pending' AND fire_at<=? "
                "ORDER BY fire_at ASC", (now.isoformat(timespec="seconds"),)
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_fired(self, reminder_id: int) -> None:
        with self.db.cursor() as cur:
            cur.execute("UPDATE reminders SET status='fired' WHERE id=?",
                        (reminder_id,))

    def reschedule(self, reminder_id: int, fire_at: datetime) -> None:
        with self.db.cursor() as cur:
            cur.execute("UPDATE reminders SET fire_at=? WHERE id=?",
                        (fire_at.isoformat(timespec="seconds"), reminder_id))

    def cancel(self, reminder_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("UPDATE reminders SET status='cancelled' WHERE id=? "
                        "AND status='pending'", (reminder_id,))
            return cur.rowcount > 0
