"""Tab 1 — the Voice Chat controller hub (full view)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from jarvis.ui.styles import VOICE_STYLE
from jarvis.ui.widgets.chat_view import ChatView


class VoiceChatTab(QWidget):
    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(VOICE_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = ChatView(controller, compact=False)
        lay.addWidget(self.view)
