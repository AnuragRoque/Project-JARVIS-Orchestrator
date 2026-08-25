"""Tab 3 — live PowerShell terminal (persistent session)."""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from jarvis.modules.terminal.tools.powershell import PowerShellEngine
from jarvis.modules.terminal.ui.terminal_panel import TerminalPanel
from jarvis.ui.styles import TERMINAL_STYLE


class TerminalTab(QWidget):
    def __init__(self, engine: PowerShellEngine | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(TERMINAL_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.engine = engine or PowerShellEngine(self)
        self.panel = TerminalPanel(engine=self.engine)
        lay.addWidget(self.panel)

    def shutdown(self) -> None:
        self.panel.shutdown()
