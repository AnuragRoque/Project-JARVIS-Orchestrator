"""On-screen reminder popups.

`ReminderPopupManager` subscribes to the ``reminder.due`` bus event (published
from the scheduler thread) and, marshalling to the GUI thread, shows a frameless
always-on-top toast. Snooze re-schedules via an injected callback.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.app.bus import bus
from jarvis.app.logsetup import get_logger
from jarvis.ui.icons import lucide_data_uri
from jarvis.ui.theme import theme_manager, toast_qss

log = get_logger("reminder.popup")


class Toast(QWidget):
    closed = pyqtSignal(object)

    def __init__(self, text: str, on_snooze: Callable[[], None] | None = None,
                 timeout_ms: int = 30000) -> None:
        super().__init__()
        self._on_snooze = on_snooze
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(340)
        pal = theme_manager.palette()
        self.setStyleSheet(toast_qss(pal))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        card = QWidget()
        card.setObjectName("ToastCard")
        shadow = QGraphicsDropShadowEffect(blurRadius=36, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 190))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        bell = lucide_data_uri("bell", color=pal.accent, size=13)
        title = QLabel(f'<img src="{bell}" width="13" height="13">&nbsp; REMINDER')
        title.setObjectName("ToastTitle")
        lay.addWidget(title)
        body = QLabel(text)
        body.setObjectName("ToastText")
        body.setWordWrap(True)
        lay.addWidget(body)

        row = QHBoxLayout()
        row.addStretch(1)
        if on_snooze is not None:
            snooze = QPushButton("Snooze 5m")
            snooze.setObjectName("ToastBtn")
            snooze.setCursor(Qt.CursorShape.PointingHandCursor)
            snooze.clicked.connect(self._snooze)
            row.addWidget(snooze)
        dismiss = QPushButton("Dismiss")
        dismiss.setObjectName("ToastPrimary")
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.clicked.connect(self.close)
        row.addWidget(dismiss)
        lay.addLayout(row)

        if timeout_ms > 0:
            QTimer.singleShot(timeout_ms, self.close)

    def _snooze(self) -> None:
        if self._on_snooze:
            try:
                self._on_snooze()
            except Exception:
                log.exception("snooze failed")
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit(self)
        super().closeEvent(event)


class ReminderPopupManager(QWidget):
    """Owns the bus subscription and stacks toasts bottom-right."""

    _due = pyqtSignal(object)

    def __init__(self, snooze_cb: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.hide()
        self._snooze_cb = snooze_cb
        self._toasts: list[Toast] = []
        self._due.connect(self._show)          # queued from the scheduler thread
        bus.subscribe("reminder.due", self._on_bus)

    def _on_bus(self, reminder: dict) -> None:
        self._due.emit(reminder)               # marshal to the GUI thread

    def _show(self, reminder: dict) -> None:
        text = reminder.get("text", "Reminder")

        def snooze() -> None:
            if self._snooze_cb:
                self._snooze_cb(text)

        toast = Toast(text, on_snooze=snooze if self._snooze_cb else None)
        toast.closed.connect(self._remove)
        self._toasts.append(toast)
        toast.show()
        self._reposition()

    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        y = screen.bottom() - 20
        for toast in reversed(self._toasts):
            toast.adjustSize()
            h = toast.sizeHint().height()
            y -= h
            toast.move(screen.right() - toast.width() - 20, y)
            y -= 8
