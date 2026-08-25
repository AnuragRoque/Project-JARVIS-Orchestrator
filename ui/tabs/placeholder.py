"""A simple 'coming soon / later phase' placeholder page."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.ui.styles import PLACEHOLDER_STYLE


class Placeholder(QWidget):
    def __init__(self, title: str, body: str, badge: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Placeholder")
        self.setStyleSheet(PLACEHOLDER_STYLE)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)

        if badge:
            b = QLabel(badge)
            b.setObjectName("PlaceholderBadge")
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b.setMaximumWidth(160)
            lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignCenter)

        t = QLabel(title)
        t.setObjectName("PlaceholderTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

        d = QLabel(body)
        d.setObjectName("PlaceholderBody")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setWordWrap(True)
        d.setMaximumWidth(520)
        lay.addWidget(d)
