"""System-tray icon and menu (no taskbar button).

The tray is the app's home base: it stays resident while windows come and go.
The Runner wires the callbacks; the tray owns none of the app logic.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def make_icon() -> QIcon:
    """A simple round 'J' badge drawn in code (no asset file needed)."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#2b62ff"))
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
    ) -> None:
        self.icon = make_icon()
        self._on_open = on_open
        self._on_quit = on_quit
        self._on_toggle_pause = on_toggle_pause

        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("JARVIS")

        menu = QMenu()
        act_open = QAction("Open JARVIS", menu)
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
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._on_open()

    def _toggle_pause(self) -> None:
        if self._on_toggle_pause is None:
            return
        paused = self._on_toggle_pause()
        self.act_pause.setText(
            "Resume activity tracking" if paused else "Pause activity tracking")

    def message(self, title: str, body: str, msecs: int = 3000) -> None:
        self.tray.showMessage(title, body, self.icon, msecs)

    def hide(self) -> None:
        self.tray.hide()
