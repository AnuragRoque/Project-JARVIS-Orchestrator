"""A flat QPushButton that shows a Lucide icon and recolours it on hover.

Qt does not tint an existing ``QIcon``, so we swap in a freshly-rendered one on
enter/leave. Used for the floating window's title-bar controls and the send
button — the base colour reads as muted, the hover colour brightens (or turns a
warning red for a close/destroy button).
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QPushButton

from jarvis.ui.icons import lucide_icon


class IconButton(QPushButton):
    def __init__(self, name: str, color: str = "#aeb6c4",
                 hover_color: str = "#ffffff", size: int = 16,
                 object_name: str = "WinBtn", tooltip: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._color = color
        self._hover = hover_color
        self._size = size
        if object_name:
            self.setObjectName(object_name)
        if tooltip:
            self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(size, size))
        self._render(self._color)

    def _render(self, color: str) -> None:
        self.setIcon(lucide_icon(self._name, color=color, size=self._size))

    def set_colors(self, color: str, hover_color: str | None = None) -> None:
        self._color = color
        if hover_color is not None:
            self._hover = hover_color
        self._render(self._color)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self._render(self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self._render(self._color)
        super().leaveEvent(event)
