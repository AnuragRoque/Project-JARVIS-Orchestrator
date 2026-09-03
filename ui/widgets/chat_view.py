"""Reusable conversation widget bound to a :class:`VoiceController`.

Both the floating orb and the Voice Chat tab embed one of these. They share a
single controller, so they always show the same conversation and the same mic
state. Construct after the controller so history replay works.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QIcon, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.icons import lucide_data_uri, lucide_icon, lucide_pixmap
from jarvis.ui.theme import dot_pixmap, permission_accent, theme_manager
from jarvis.ui.widgets.icon_button import IconButton


class MicButton(QPushButton):
    """Circular mic button with an animated glow ring while active.

    ``idle_icon`` / ``active_icon`` let the two mics read differently: the big
    hands-free **Live** button shows a waveform, the one-shot recorder shows a
    plain mic — and both switch to a stop-square while active.
    """

    def __init__(self, object_name: str = "Mic", icon_px: int = 24,
                 idle_icon: str = "mic", active_icon: str = "square",
                 idle_color: str = "#ffffff", active_color: str = "#ffffff") -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_px = icon_px
        self._idle_icon = idle_icon
        self._active_icon = active_icon
        self._idle_color = idle_color
        self._active_color = active_color
        self._recording = False
        self.setIconSize(QSize(icon_px, icon_px))
        self._render()
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

    def _render(self) -> None:
        icon = self._active_icon if self._recording else self._idle_icon
        color = self._active_color if self._recording else self._idle_color
        self.setIcon(lucide_icon(icon, color=color, size=self._icon_px))

    def set_idle_color(self, color: str) -> None:
        self._idle_color = color
        if not self._recording:
            self._render()

    def set_recording(self, on: bool) -> None:
        self._recording = on
        self.setProperty("recording", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._render()
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
        self.header.setIconSize(QSize(13, 13))
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
        state = "" if self._result or not self._busy else " · running…"
        return f"  {'View ' if not self._open else ''}{pretty}{state}"

    def _render_header(self) -> None:
        chevron = "chevron-down" if self._open else "chevron-right"
        self.header.setIcon(lucide_icon(chevron, color="#7f9ac0", size=13))
        self.header.setText(self._label())

    def _running(self, busy: bool) -> None:
        self._busy = busy
        self._render_header()

    def _toggle(self) -> None:
        self._open = not self._open
        self.detail.setVisible(self._open)
        self._render_header()
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

        # Permission-mode toggle (shared, persisted via the controller). The dot
        # + shield colour signal the "robot mood": blue safe, amber supervised,
        # red unrestrained.
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self.shield = QLabel()
        self.shield.setObjectName("Subtitle")
        mode_row.addWidget(self.shield)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModeCombo")
        for label in ("Auto", "Partial", "Manual"):
            a, _ = permission_accent(label.lower())
            self.mode_combo.addItem(QIcon(dot_pixmap(a, 11)), label)
        self.mode_combo.setCurrentText(self.ctrl.permission_mode.capitalize())
        self.mode_combo.currentTextChanged.connect(
            lambda t: self.ctrl.set_permission_mode(t.lower()))
        self.mode_combo.setToolTip(
            "Auto: run everything · Partial: ask before risky actions · "
            "Manual: ask before anything but read-only")
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)
        self._recolor_shield()

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

        # The big hands-free "Live" button — a waveform, distinct from the
        # one-shot recorder mic below.
        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.mic = MicButton("Mic", icon_px=26, idle_icon="audio-lines",
                             active_icon="square")
        self.mic.setToolTip("Live hands-free conversation (tap to stop)")
        self.mic.clicked.connect(self.ctrl.toggle_live)
        mic_row.addWidget(self.mic)
        mic_row.addStretch()
        lay.addLayout(mic_row)

        # Input field with the one-shot recorder mic tucked inside it.
        self.input = QLineEdit()
        self.input.setObjectName("Input")
        self.input.setPlaceholderText("Type a message…")
        self.input.returnPressed.connect(self._send_typed)
        self.input.installEventFilter(self)
        self.mic_small = MicButton("MicMini", icon_px=16, idle_icon="mic",
                                   active_icon="square")
        self.mic_small.setToolTip("Record one message")
        self.mic_small.clicked.connect(self.ctrl.toggle_record)

        self.input_wrap = QFrame()
        self.input_wrap.setObjectName("InputWrap")
        wrap_lay = QHBoxLayout(self.input_wrap)
        wrap_lay.setContentsMargins(4, 3, 6, 3)
        wrap_lay.setSpacing(2)
        wrap_lay.addWidget(self.input, 1)
        wrap_lay.addWidget(self.mic_small)

        send = IconButton("send", color="#ffffff", hover_color="#ffffff",
                          size=18, object_name="Send", tooltip="Send")
        send.clicked.connect(self._send_typed)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        input_row.addWidget(self.input_wrap, 1)
        input_row.addWidget(send)
        lay.addLayout(input_row)

        self._recolor_icons()
        theme_manager.changed.connect(self._recolor_icons)

    # -------------------------------------------------------- icon colours
    def _recolor_shield(self) -> None:
        accent, _ = permission_accent(self.ctrl.permission_mode)
        self.shield.setPixmap(lucide_pixmap("shield-check", color=accent, size=14))

    def _recolor_icons(self) -> None:
        pal = theme_manager.palette()
        self.mic_small.set_idle_color(pal.subtext)
        self._recolor_shield()

    def eventFilter(self, obj, event):  # noqa: ANN001
        if obj is self.input and event.type() in (
                QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            focused = event.type() == QEvent.Type.FocusIn
            self.input_wrap.setProperty("focused", "true" if focused else "false")
            self.input_wrap.style().unpolish(self.input_wrap)
            self.input_wrap.style().polish(self.input_wrap)
        return super().eventFilter(obj, event)

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
        c.error_occurred.connect(self._on_error_msg)
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
        self._recolor_shield()

    def _on_error_msg(self, message: str) -> None:
        uri = lucide_data_uri("alert-triangle", color="#ff8791", size=12)
        self._add_bubble("system",
                         f'<img src="{uri}" width="12" height="12">&nbsp; {message}')

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
