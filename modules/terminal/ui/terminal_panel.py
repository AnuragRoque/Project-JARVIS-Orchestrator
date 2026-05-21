from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.modules.terminal.tools.powershell import PowerShellEngine


class CommandLineEdit(QLineEdit):
    """QLineEdit with history recall via Up/Down arrow keys."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._index = 0

    def remember(self, command: str) -> None:
        if command and (not self._history or self._history[-1] != command):
            self._history.append(command)
        self._index = len(self._history)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up and self._history:
            self._index = max(0, self._index - 1)
            self.setText(self._history[self._index])
            self.end(False)
            return
        if key == Qt.Key.Key_Down and self._history:
            self._index = min(len(self._history), self._index + 1)
            self.setText("" if self._index == len(self._history) else self._history[self._index])
            self.end(False)
            return
        super().keyPressEvent(event)


class TerminalPanel(QWidget):
    """Terminal Panel displaying persistent PowerShell stdout and providing command input."""

    def __init__(self, engine: PowerShellEngine | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine or PowerShellEngine(self)
        self.engine.output_received.connect(self._append_text)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header = QLabel("  TERMINAL · PowerShell")
        header.setObjectName("panelHeader")
        header_row.addWidget(header)
        header_row.addStretch(1)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("miniButton")
        clear_btn.clicked.connect(lambda: self.output.clear())
        header_row.addWidget(clear_btn)

        restart_btn = QPushButton("Restart")
        restart_btn.setObjectName("miniButton")
        restart_btn.clicked.connect(self.engine.start_session)
        header_row.addWidget(restart_btn)
        layout.addLayout(header_row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setObjectName("terminalOutput")
        self.output.setFont(QFont("Cascadia Mono", 10))
        self.output.setMaximumBlockCount(5000)
        layout.addWidget(self.output, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        prompt = QLabel("PS ❯")
        prompt.setObjectName("terminalPrompt")
        prompt.setFont(QFont("Cascadia Mono", 10))
        input_row.addWidget(prompt)

        self.input = CommandLineEdit()
        self.input.setObjectName("terminalInput")
        self.input.setFont(QFont("Cascadia Mono", 10))
        self.input.setPlaceholderText("type a command… (↑/↓ history)")
        self.input.returnPressed.connect(self._send_command)
        input_row.addWidget(self.input, stretch=1)
        layout.addLayout(input_row)

    def _send_command(self) -> None:
        command = self.input.text()
        self.input.remember(command)
        self.input.clear()
        self.engine.send_interactive(command)

    def _append_text(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.ensureCursorVisible()

    def run_captured(self, command: str, on_done) -> None:
        self.input.setEnabled(False)

        def callback(result):
            self.input.setEnabled(True)
            on_done(result)

        self.engine.run_captured(command, callback)

    def shutdown(self) -> None:
        self.engine.shutdown()
