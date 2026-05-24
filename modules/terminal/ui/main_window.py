from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from jarvis.modules.terminal.ui.chat_panel import ChatPanel
from jarvis.modules.terminal.ui.terminal_panel import TerminalPanel

STYLESHEET = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #e0e0e0; }
#panelFrame {
    background-color: #252537;
    border: 1px solid #333349;
    border-radius: 8px;
}
#panelHeader {
    color: #9aa0b5;
    font-weight: 700;
    letter-spacing: 1px;
    font-size: 11px;
    padding: 2px 0;
}
#terminalOutput {
    background-color: #0c0c0c;
    border: 1px solid #2c2c3f;
    border-radius: 6px;
    padding: 6px 8px;
    color: #d4d4d4;
}
#terminalPrompt { color: #5ef19a; font-weight: 700; padding-left: 2px; }
#terminalInput {
    background-color: #0c0c0c;
    border: 1px solid #2c2c3f;
    border-radius: 6px;
    padding: 6px 8px;
    color: #d4d4d4;
}
#terminalInput:focus { border: 1px solid #5ef19a; }
#chatView {
    background-color: #16161f;
    border: 1px solid #2c2c3f;
    border-radius: 6px;
    padding: 6px;
    color: #e0e0e0;
}
QLineEdit, QComboBox {
    background-color: #16161f;
    border: 1px solid #2c2c3f;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e0e0e0;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #4fc3f7; }
QPushButton {
    background-color: #3a3a5a;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    color: #e0e0e0;
    font-weight: 600;
}
QPushButton:hover { background-color: #4a4a70; }
QPushButton:pressed { background-color: #33334f; }
#miniButton { padding: 3px 10px; font-size: 11px; }
#statusLabel { color: #e0b341; font-weight: 600; font-size: 11px; }
#stopButton { background-color: #5a2a2a; }
#stopButton:hover { background-color: #7a3535; }
#stopButton:disabled { background-color: #333349; color: #666; }
QSplitter::handle { background-color: #333349; width: 4px; }
"""


class MainWindow(QMainWindow):
    """Jarvis Tools main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Jarvis Tools — Desktop AI Agent")
        self.resize(1200, 700)
        self.setStyleSheet(STYLESHEET)

        self.chat = ChatPanel()
        self.terminal = TerminalPanel()
        self.chat.attach_terminal(self.terminal)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._wrap(self.chat))
        splitter.addWidget(self._wrap(self.terminal))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 600])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    @staticmethod
    def _wrap(panel: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panelFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(panel)
        return frame

    def closeEvent(self, event) -> None:
        self.chat.shutdown()
        self.terminal.shutdown()
        super().closeEvent(event)
