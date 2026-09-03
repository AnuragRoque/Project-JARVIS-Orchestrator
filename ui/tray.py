"""System-tray icon and menu (no taskbar button).

The tray is the app's home base: it stays resident while windows come and go.
The Runner wires the callbacks; the tray owns none of the app logic.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def make_icon(color: str = "#2b62ff") -> QIcon:
    """A simple round 'J' badge drawn in code (no asset file needed).

    ``color`` reflects the permission mode so the tray, like the orb, signals how
    much autonomy JARVIS has (blue Manual / amber Partial / red Auto)."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor("white"))
    font = p.font()
    font.setPixelSize(34)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "J")
    p.end()
    return QIcon(pix)


class Tray:
    def __init__(
        self,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        on_toggle_pause: Callable[[], bool] | None = None,
        on_mini: Callable[[], None] | None = None,
    ) -> None:
        self.icon = make_icon()
        self._on_open = on_open
        self._on_quit = on_quit
        self._on_toggle_pause = on_toggle_pause
        self._on_mini = on_mini

        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("JARVIS")

        menu = QMenu()
        if on_mini is not None:
            act_mini = QAction("Quick bar", menu)
            act_mini.triggered.connect(lambda: on_mini())
            menu.addAction(act_mini)
        act_open = QAction("Open full window", menu)
        act_open.triggered.connect(lambda: on_open())
        menu.addAction(act_open)

        if on_toggle_pause is not None:
            self.act_pause = QAction("Pause activity tracking", menu)
            self.act_pause.triggered.connect(self._toggle_pause)
            menu.addAction(self.act_pause)

        menu.addSeparator()
        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(lambda: on_quit())
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_activated(self, reason) -> None:
        # Single click → the quick bar above the tray; double click → full window.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            (self._on_mini or self._on_open)()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._on_open()

    def _toggle_pause(self) -> None:
        if self._on_toggle_pause is None:
            return
        paused = self._on_toggle_pause()
        self.act_pause.setText(
            "Resume activity tracking" if paused else "Pause activity tracking")

    def set_accent(self, color: str) -> None:
        """Retint the tray badge (called when the permission mode changes)."""
        self.icon = make_icon(color)
        self.tray.setIcon(self.icon)

    def message(self, title: str, body: str, msecs: int = 3000) -> None:
        self.tray.showMessage(title, body, self.icon, msecs)

    def hide(self) -> None:
        self.tray.hide()
