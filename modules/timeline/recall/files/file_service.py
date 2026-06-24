"""Background service that periodically imports recent file activity.

Runs a low-frequency scan (default every 5 minutes) of the Windows Recent
Items folder and records new/updated file activity through the repository.
This is intentionally lightweight and native — no filesystem watchers.
"""
from __future__ import annotations

import threading

from ..config import get_config
from ..logging_setup import get_logger
from ..storage import get_repository
from .recent_items import scan_recent_files

log = get_logger("files.service")


def scan_once() -> int:
    """Scan Recent Items and upsert file events. Returns count recorded."""
    cfg = get_config()
    if cfg.private_mode:
        return 0
    repo = get_repository()
    recorded = 0
    for rf in scan_recent_files():
        # Honour process exclusions loosely by extension? Not applicable; we
        # simply record the file. Private/retention handled by repo/config.
        fid = repo.record_file_event(
            path=rf.path, application=None,
            last_activity=rf.last_activity, source="recent",
        )
        if fid is not None:
            recorded += 1
    if recorded:
        log.info("File recall imported %d recent files", recorded)
    return recorded


class FileRecallService:
    def __init__(self, interval_seconds: float = 300.0):
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="file-recall", daemon=True)
        self._thread.start()
        log.info("File recall service started (every %.0fs)", self.interval)

    def _run(self) -> None:
        # Initial scan shortly after startup, then on the interval.
        while not self._stop.is_set():
            try:
                scan_once()
                # Piggyback retention cleanup on this low-frequency loop.
                get_repository().apply_retention()
            except Exception:
                log.exception("File recall scan failed")
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("File recall service stopped")
