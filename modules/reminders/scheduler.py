"""Background scheduler that fires due reminders.

A daemon thread polls the store every few seconds. For each due reminder it calls
``on_due(reminder)`` and marks it fired (recurring reminders are rescheduled).
Survives restarts because pending reminders live in SQLite, not memory.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Callable

from jarvis.app.logsetup import get_logger
from .store import ReminderStore

log = get_logger("reminders.scheduler")

_RECUR = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "hourly": timedelta(hours=1),
}


class ReminderScheduler:
    def __init__(self, store: ReminderStore,
                 on_due: Callable[[dict], None], poll_seconds: float = 10.0) -> None:
        self.store = store
        self.on_due = on_due
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="reminders", daemon=True)
        self._thread.start()
        log.info("Reminder scheduler started (poll %.0fs)", self.poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        log.info("Reminder scheduler stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("Reminder tick failed")
            self._stop.wait(self.poll_seconds)

    def _tick(self) -> None:
        for r in self.store.due():
            try:
                self.on_due(r)
            except Exception:
                log.exception("on_due failed for reminder %s", r.get("id"))
            step = _RECUR.get((r.get("recurrence") or "").lower())
            if step:
                self.store.reschedule(r["id"], datetime.now() + step)
            else:
                self.store.mark_fired(r["id"])
