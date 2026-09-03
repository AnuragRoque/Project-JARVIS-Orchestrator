"""Tab 3 — live PowerShell terminal (persistent session)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from jarvis.modules.terminal.tools.powershell import PowerShellEngine
from jarvis.modules.terminal.ui.terminal_panel import TerminalPanel
from jarvis.ui.theme import terminal_qss, theme_manager


class TerminalTab(QWidget):
    def __init__(self, engine: PowerShellEngine | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apply_theme()
        theme_manager.changed.connect(self._apply_theme)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.engine = engine or PowerShellEngine(self)
        self.panel = TerminalPanel(engine=self.engine)
        lay.addWidget(self.panel)

    def _apply_theme(self) -> None:
        self.setStyleSheet(terminal_qss(theme_manager.palette()))

    def shutdown(self) -> None:
        self.panel.shutdown()
