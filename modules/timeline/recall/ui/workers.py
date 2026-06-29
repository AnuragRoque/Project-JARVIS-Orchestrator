"""Background workers so slow operations never block the Qt UI thread."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal as Signal

from ..logging_setup import get_logger
from ..search import get_search_engine
from ..semantic import get_semantic_service

log = get_logger("ui.workers")


class _Signals(QObject):
    done = Signal(str, str, list)   # query, mode, results
    failed = Signal(str, str)       # query, error


class SearchWorker(QRunnable):
    """Runs keyword or semantic search off the UI thread."""

    def __init__(self, query: str, mode: str):
        super().__init__()
        self.query = query
        self.mode = mode
        self.signals = _Signals()

    def run(self) -> None:
        try:
            if self.mode == "semantic":
                svc = get_semantic_service()
                if not svc.available:
                    self.signals.failed.emit(
                        self.query,
                        "Semantic search needs sentence-transformers + faiss.")
                    return
                results = svc.search(self.query)
            else:
                results = get_search_engine().search(self.query)
            self.signals.done.emit(self.query, self.mode, results)
        except Exception as exc:  # noqa: BLE001
            log.exception("Search worker failed")
            self.signals.failed.emit(self.query, str(exc))


class SemanticBuildWorker(QRunnable):
    """Builds/updates the semantic index in the background."""

    def __init__(self):
        super().__init__()
        self.signals = _Signals()

    def run(self) -> None:
        try:
            svc = get_semantic_service()
            if svc.available:
                added = svc.build()
                self.signals.done.emit("", "build", [added])
        except Exception as exc:  # noqa: BLE001
            log.exception("Semantic build failed")
            self.signals.failed.emit("", str(exc))
