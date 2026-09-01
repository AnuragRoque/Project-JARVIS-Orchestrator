"""Reusable conversation widget bound to a :class:`VoiceController`.

Both the floating orb and the Voice Chat tab embed one of these. They share a
single controller, so they always show the same conversation and the same mic
state. Construct after the controller so history replay works.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MicButton(QPushButton):
    """Circular mic button with an animated glow ring while active."""

    def __init__(self, object_name: str = "Mic") -> None:
        super().__init__("\U0001F3A4")  # 🎤
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._glow = 0.0
        self._anim = QPropertyAnimation(self, b"glow")
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(900)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, v: float) -> None:
        self._glow = v
        self.update()

    glow = pyqtProperty(float, fget=get_glow, fset=set_glow)

    def set_recording(self, on: bool) -> None:
        self.setProperty("recording", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if on:
            self._anim.start()
        else:
            self._anim.stop()
            self.set_glow(0.0)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        if self._glow > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            radius = self.width() / 2 + self._glow * 8
            color = QColor(255, 93, 122)
            color.setAlphaF(0.35 * (1 - self._glow))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            c = self.rect().center()
            p.drawEllipse(c, int(radius), int(radius))
            p.end()
        super().paintEvent(event)


class Bubble(QWidget):
    """A single chat message aligned left/right by role."""

    def __init__(self, role: str, text: str, max_width: int = 460) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.label.setObjectName(f"Bubble_{role}")
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(max_width)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == "user":
            lay.addStretch()
            lay.addWidget(self.label)
        elif role == "assistant":
            lay.addWidget(self.label)
            lay.addStretch()
        else:  # system / status
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(self.label)

    def set_text(self, text: str) -> None:
        self.label.setText(text)


class StepView(QWidget):
    """A collapsed 'View command' chip (left-aligned) that expands to show the
    tool's command/arguments and its result. Keeps commands out of the way while
    staying one click from full detail — shown *under* the reply, never centred.
    """

    def __init__(self, name: str, args: str, max_width: int = 460) -> None:
        super().__init__()
        self._name = name
        self._args = args or ""
        self._result = ""
        self._open = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        col = QVBoxLayout()
        col.setSpacing(4)

        self.header = QPushButton()
        self.header.setObjectName("StepHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setMaximumWidth(max_width)
        self.header.clicked.connect(self._toggle)

        self.detail = QLabel()
        self.detail.setObjectName("StepDetail")
        self.detail.setWordWrap(True)
        self.detail.setMaximumWidth(max_width)
        self.detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.hide()

        col.addWidget(self.header)
        col.addWidget(self.detail)
        row.addLayout(col)
        row.addStretch(1)
        self._running(True)

    def _label(self) -> str:
        pretty = "command" if self._name == "run_powershell" else self._name.replace("_", " ")
        arrow = "▾" if self._open else "▸"
        state = "" if self._result or not self._busy else " · running…"
        return f"{arrow}  {'View ' if not self._open else ''}{pretty}{state}"

    def _running(self, busy: bool) -> None:
        self._busy = busy
        self.header.setText(self._label())

    def _toggle(self) -> None:
        self._open = not self._open
        self.detail.setVisible(self._open)
        self.header.setText(self._label())
        if self._open:
            self._render_detail()

    def _render_detail(self) -> None:
        parts = []
        if self._args:
            parts.append(f"$ {self._args}")
        if self._result:
            parts.append(self._result)
        self.detail.setText("\n".join(parts) or "(no output)")

    def set_result(self, preview: str) -> None:
        self._result = preview or ""
        self._running(False)
        if self._open:
            self._render_detail()


class ChatView(QWidget):
    """Conversation + input, bound to a shared VoiceController."""

    def __init__(self, controller, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctrl = controller
        self.compact = compact
        self._max_bubble = 300 if compact else 560
        self._stream_bubble: Bubble | None = None
        self._stream_text = ""
        self._step_view: StepView | None = None

        self._build()
        self._replay_history()
        self._wire()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        m = 12 if self.compact else 18
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(10)

        # Permission-mode toggle (shared, persisted via the controller).
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        shield = QLabel("🛡")
        shield.setObjectName("Subtitle")
        mode_row.addWidget(shield)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModeCombo")
        self.mode_combo.addItems(["Auto", "Partial", "Manual"])
        self.mode_combo.setCurrentText(self.ctrl.permission_mode.capitalize())
        self.mode_combo.currentTextChanged.connect(
            lambda t: self.ctrl.set_permission_mode(t.lower()))
        self.mode_combo.setToolTip(
            "Auto: run everything · Partial: ask before risky actions · "
            "Manual: ask before anything but read-only")
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Chat")
        self.chat_lay = QVBoxLayout(host)
        self.chat_lay.setContentsMargins(0, 0, 0, 0)
        self.chat_lay.setSpacing(8)
        self.chat_lay.addStretch()
        self.scroll.setWidget(host)
        lay.addWidget(self.scroll, 1)

        if not self.compact and not self.ctrl.history:
            self._add_bubble(
                "system",
                "Tap the orb for a hands-free conversation, use the small mic for "
                "one line, or just type.",
            )

        self.status = QLabel("Ready")
        self.status.setObjectName("Status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status)

        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.mic = MicButton("Mic")
        self.mic.clicked.connect(self.ctrl.toggle_live)
        mic_row.addWidget(self.mic)
        mic_row.addStretch()
        lay.addLayout(mic_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.mic_small = MicButton("MicMini")
        self.mic_small.clicked.connect(self.ctrl.toggle_record)
        self.input = QLineEdit()
        self.input.setObjectName("Input")
        self.input.setPlaceholderText("Type a message…")
        self.input.returnPressed.connect(self._send_typed)
        send = QPushButton("Send")
        send.setObjectName("Ghost")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send_typed)
        input_row.addWidget(self.mic_small)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(send)
        lay.addLayout(input_row)

    # ------------------------------------------------------------- helpers
    def _add_bubble(self, role: str, text: str) -> Bubble:
        bubble = Bubble(role, text, max_width=self._max_bubble)
        self.chat_lay.insertWidget(self.chat_lay.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _add_step(self, name: str, args: str) -> StepView:
        step = StepView(name, args, max_width=self._max_bubble)
        self.chat_lay.insertWidget(self.chat_lay.count() - 1, step)
        self._scroll_to_bottom()
        return step

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _replay_history(self) -> None:
        for turn in self.ctrl.history:
            role = turn.get("role")
            if role in ("user", "assistant"):
                self._add_bubble(role, turn.get("content", ""))

    def _send_typed(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.ctrl.send_text(text)

    def prefill(self, text: str) -> None:
        """Put text in the input box and focus it (does not send)."""
        self.input.setText(text)
        self.input.setFocus()
        self.input.setCursorPosition(len(text))

    # --------------------------------------------------- controller signals
    def _wire(self) -> None:
        c = self.ctrl
        c.user_said.connect(lambda t: self._add_bubble("user", t))
        c.reply_started.connect(self._on_reply_started)
        c.reply_chunk.connect(self._on_reply_chunk)
        c.reply_finished.connect(self._on_reply_finished)
        c.status_changed.connect(self.status.setText)
        c.error_occurred.connect(lambda m: self._add_bubble("system", f"⚠ {m}"))
        c.busy_changed.connect(self._on_busy)
        c.recording_changed.connect(self.mic_small.set_recording)
        c.listening_changed.connect(self._on_listening)
        c.tool_started.connect(self._on_tool_started)
        c.tool_finished.connect(self._on_tool_finished)
        c.permission_mode_changed.connect(self._on_mode_changed)

    def _on_mode_changed(self, mode: str) -> None:
        want = mode.capitalize()
        if self.mode_combo.currentText() != want:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentText(want)
            self.mode_combo.blockSignals(False)

    def _on_reply_started(self) -> None:
        self._stream_text = ""
        self._stream_bubble = self._add_bubble("assistant", "…")

    def _on_reply_chunk(self, delta: str) -> None:
        self._stream_text += delta
        if self._stream_bubble is not None:
            self._stream_bubble.set_text(self._stream_text)
            self._scroll_to_bottom()

    def _on_reply_finished(self, text: str) -> None:
        if self._stream_bubble is not None:
            self._stream_bubble.set_text(text or "…")
        self._stream_bubble = None
        self._stream_text = ""

    def _on_tool_started(self, name: str, args: str) -> None:
        self._step_view = self._add_step(name, args[:400])

    def _on_tool_finished(self, name: str, preview: str) -> None:
        if self._step_view is not None:
            self._step_view.set_result(preview[:600])
            self._step_view = None
        else:
            step = self._add_step(name, "")
            step.set_result(preview[:600])
        self._scroll_to_bottom()

    def _on_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.mic_small.setEnabled(not busy and not self.ctrl.is_live)

    def _on_listening(self, live: bool) -> None:
        self.mic.set_recording(live)
        self.mic_small.setEnabled(not live and not self.ctrl.is_busy)
