"""Tab 1 — the Voice Chat controller hub (full view)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from jarvis.ui.theme import glass_qss, theme_manager
from jarvis.ui.widgets.chat_view import ChatView


class VoiceChatTab(QWidget):
    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apply_theme()
        theme_manager.changed.connect(self._apply_theme)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = ChatView(controller, compact=False)
        lay.addWidget(self.view)

    def _apply_theme(self) -> None:
        self.setStyleSheet(glass_qss(theme_manager.palette()))
