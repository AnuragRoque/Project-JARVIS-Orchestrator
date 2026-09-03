"""Tab 2 — Activity Timeline (embeds the ported recall window)."""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from jarvis.modules.timeline.recall.ui.main_window import MainWindow as RecallWindow
from jarvis.modules.timeline.recall.ui.theme import stylesheet


class TimelineTab(QWidget):
    def __init__(self, tracker=None, on_send_to_jarvis=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(stylesheet(dark=True))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.window = RecallWindow(tracker=tracker)
        # Embedded: don't let it intercept the app's close into hide-to-tray.
        self.window.close_to_tray = False
        if on_send_to_jarvis is not None:
            self.window.send_to_jarvis = on_send_to_jarvis
        # Wrap it so its large minimum size can't force the whole app window
        # past the screen edge; it scrolls internally on small windows.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.window)
        lay.addWidget(scroll)
