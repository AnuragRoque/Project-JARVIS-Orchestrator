"""Tab 2 — Activity Timeline (embeds the ported recall window)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from jarvis.modules.timeline.recall.ui.main_window import MainWindow as RecallWindow
from jarvis.modules.timeline.recall.ui.theme import stylesheet


class TimelineTab(QWidget):
    def __init__(self, tracker=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(stylesheet(dark=True))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.window = RecallWindow(tracker=tracker)
        # Embedded: don't let it intercept the app's close into hide-to-tray.
        self.window.close_to_tray = False
        lay.addWidget(self.window)
