"""Background workers so network / audio / TTS never block the UI thread.

Generic QThreadPool tasks reused across the UI (originally from the voice core).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class _Signals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()
    chunk = pyqtSignal(str)


class Task(QRunnable):
    """Run ``fn(*args, **kwargs)`` on a thread-pool thread and emit its result."""

    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _Signals()

    def run(self) -> None:
        try:
            out = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(out)
        finally:
            self.signals.finished.emit()


class StreamTask(QRunnable):
    """Run a streaming fn that takes an ``on_chunk`` callback; relays chunks live."""

    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _Signals()

    def run(self) -> None:
        try:
            out = self.fn(*self.args, on_chunk=self.signals.chunk.emit, **self.kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(out)
        finally:
            self.signals.finished.emit()
