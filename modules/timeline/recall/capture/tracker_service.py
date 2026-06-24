"""The activity tracker service.

Runs a background thread that polls the foreground window and merges
consecutive observations of the same window into a single session, which is
flushed to the repository when:
  * the active window changes, or
  * the window disappears / becomes idle / tracking is paused, or
  * the service stops.

Design decisions
----------------
* We time sessions by *observation*: a session's ``end_time`` is the moment we
  last confirmed the window was active, never a future time. This keeps
  durations honest even if the app crashes.
* Idle time (no keyboard/mouse for ``idle_timeout_seconds``) ends the current
  session so we don't record hours of an untouched screen.
* Excluded processes and empty titles are dropped per configuration.
* The poll is deliberately cheap: one Win32 call + a cached psutil lookup.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import get_config
from ..logging_setup import get_logger
from ..storage import get_repository
from .window_tracker import WindowSnapshot, get_active_window, get_idle_seconds

log = get_logger("capture.tracker")


def _now() -> datetime:
    # Naive UTC to match the storage convention (see models.utcnow).
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class _OpenSession:
    snapshot: WindowSnapshot
    start_time: datetime
    last_seen: datetime


class TrackerService:
    def __init__(self):
        self.repo = get_repository()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._open: _OpenSession | None = None
        self._paused = False
        self._lock = threading.Lock()
        # Simple counters for diagnostics / UI.
        self.sessions_recorded = 0

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="tracker", daemon=True
        )
        self._thread.start()
        log.info("Tracker service started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._flush()
        log.info("Tracker service stopped")

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self._flush_locked()
        log.info("Tracking paused")

    def resume(self) -> None:
        with self._lock:
            self._paused = False
        log.info("Tracking resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ------------------------------------------------------------- main loop
    def _run(self) -> None:
        while not self._stop.is_set():
            cfg = get_config()
            interval = max(0.5, cfg.poll_interval_seconds)
            try:
                self._tick(cfg)
            except Exception:  # never let the loop die
                log.exception("Tracker tick failed")
            self._stop.wait(interval)

    def _tick(self, cfg) -> None:
        with self._lock:
            # Respect pause / global tracking switch / private mode.
            if self._paused or not cfg.tracking_enabled or cfg.private_mode:
                self._flush_locked()
                return

            # Idle -> end current session, record nothing further until active.
            if cfg.idle_timeout_seconds > 0 and \
                    get_idle_seconds() >= cfg.idle_timeout_seconds:
                self._flush_locked()
                return

            snap = get_active_window()
            if snap is None:
                return

            # Empty/uninteresting titles.
            if cfg.ignore_empty_titles and not snap.window_title.strip():
                self._flush_locked()
                return

            # Excluded processes.
            if any(snap.process_name == p.lower()
                   for p in cfg.excluded_processes):
                self._flush_locked()
                return

            now = _now()
            if self._open is None:
                self._open = _OpenSession(snap, now, now)
                return

            if snap.identity() == self._open.snapshot.identity():
                # Same window: extend session if the gap is within threshold.
                gap = (now - self._open.last_seen).total_seconds()
                if gap <= cfg.session_merge_gap_seconds:
                    self._open.last_seen = now
                else:
                    # Long gap on the same title -> new session.
                    self._flush_locked()
                    self._open = _OpenSession(snap, now, now)
            else:
                # Window changed: flush old, open new.
                self._flush_locked()
                self._open = _OpenSession(snap, now, now)

    # ------------------------------------------------------------- flushing
    def _flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._open is None:
            return
        s = self._open
        self._open = None
        snap = s.snapshot
        sid = self.repo.record_session(
            process_name=snap.process_name,
            exe_path=snap.exe_path,
            window_title=snap.window_title,
            pid=snap.pid,
            start_time=s.start_time,
            end_time=s.last_seen,
            kind=snap.kind,
        )
        if sid is not None:
            self.sessions_recorded += 1
            log.debug("Recorded session %d: %s (%s)", sid,
                      snap.window_title[:60], snap.process_name)
