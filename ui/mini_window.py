"""The quick bar — a tiny flyout docked above the system-tray icon.

Clicking the tray icon pops this up just above the taskbar: a one-line
controller with a **Live** toggle, a compact full-width transcript, an input
with an inline mic + send, and the permission selector — plus buttons to grow
into the floating orb or the full window.

The transcript is deliberately *not* the bubble chat: messages run full width,
one after another (you, then JARVIS), scrollable up to a capped height with the
scrollbar hidden. A small activity strip animates what JARVIS is doing right
now — listening while Live is on, reacting while you speak, and thinking dots
while it works. Only one surface (quick bar / orb / full window) is shown at a
time — the Runner enforces that.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.icons import lucide_data_uri, lucide_icon
from jarvis.ui.theme import dot_pixmap, glass_qss, permission_accent, theme_manager
from jarvis.ui.widgets.activity import TypingDots, WaveBars
from jarvis.ui.widgets.chat_view import MicButton
from jarvis.ui.widgets.icon_button import IconButton

WIDTH = 360
MARGIN = 8
MAX_MESSAGES = 30


class Message(QFrame):
    """A single full-width conversation row: a small role caption over a
    word-wrapped body. Spans the whole width — no left/right bubble alignment."""

    def __init__(self, role: str, text: str = "") -> None:
        super().__init__()
        user = role == "user"
        self.setObjectName("MsgUser" if user else "MsgAssistant")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 9)
        lay.setSpacing(2)
        cap = QLabel("YOU" if user else "JARVIS")
        cap.setObjectName("MsgRoleUser" if user else "MsgRole")
        self.body = QLabel(text)
        self.body.setObjectName("MsgBodyUser" if user else "MsgBody")
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(cap)
        lay.addWidget(self.body)

    def set_text(self, text: str) -> None:
        self.body.setText(text)


class MiniBar(QWidget):
    request_floating = pyqtSignal()
    request_maximise = pyqtSignal()

    def __init__(self, controller) -> None:
        super().__init__()
        self.ctrl = controller
        self._reply_msg: Message | None = None
        self._reply_text = ""

        # activity state (drives the strip animations)
        self._live = False
        self._busy = False
        self._recording = False
        self._hearing = False
        self._tts = False
        self._status_text = "Ready"

        self.setWindowTitle("JARVIS")
        self.setFixedWidth(WIDTH)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build()
        self._apply_theme()
        self._wire()
        self._replay()
        theme_manager.changed.connect(self._apply_theme)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        self.card = QWidget()
        self.card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(blurRadius=36, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 190))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        col = QVBoxLayout(self.card)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(8)

        # Header: title + window buttons
        head = QHBoxLayout()
        head.setSpacing(2)
        title = QLabel("JARVIS")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_orb = IconButton("bot", size=15, tooltip="Open the floating orb")
        self.btn_orb.clicked.connect(self.request_floating.emit)
        self.btn_max = IconButton("maximize-2", size=15, tooltip="Open the full window")
        self.btn_max.clicked.connect(self.request_maximise.emit)
        self.btn_close = IconButton("x", size=15, tooltip="Close", hover_color="#ff6b7a")
        self.btn_close.clicked.connect(self.hide)
        for b in (self.btn_orb, self.btn_max, self.btn_close):
            head.addWidget(b)
        col.addLayout(head)

        # Controls: Live toggle + permission mode. Both are fixed-size so toggling
        # the Live label ("Live" ⇆ "Live · on") can never reflow into the combo.
        ctrls = QHBoxLayout()
        ctrls.setSpacing(8)
        self.live_btn = QPushButton("  Live")
        self.live_btn.setObjectName("LiveToggle")
        self.live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_btn.setToolTip("Live hands-free conversation on/off")
        self.live_btn.setFixedSize(108, 30)
        self.live_btn.clicked.connect(self.ctrl.toggle_live)
        ctrls.addWidget(self.live_btn)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModeCombo")
        self.mode_combo.setFixedSize(104, 30)
        for label in ("Auto", "Partial", "Manual"):
            accent, _ = permission_accent(label.lower())
            self.mode_combo.addItem(QIcon(dot_pixmap(accent, 11)), label)
        self.mode_combo.setCurrentText(self.ctrl.permission_mode.capitalize())
        self.mode_combo.currentTextChanged.connect(
            lambda t: self.ctrl.set_permission_mode(t.lower()))
        ctrls.addWidget(self.mode_combo)
        ctrls.addStretch(1)
        col.addLayout(ctrls)

        # Full-width transcript: you, then JARVIS — scrollable up to a cap, with
        # the scrollbar hidden (the wheel still scrolls).
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(70)
        self.scroll.setMaximumHeight(210)
        host = QWidget()
        host.setObjectName("Chat")
        self.msg_lay = QVBoxLayout(host)
        self.msg_lay.setContentsMargins(0, 0, 0, 0)
        self.msg_lay.setSpacing(7)
        self.msg_lay.addStretch()
        self.scroll.setWidget(host)
        col.addWidget(self.scroll)

        # Activity strip: an equalizer for live/speaking, dots for thinking.
        act = QHBoxLayout()
        act.setSpacing(7)
        self.bars = WaveBars()
        self.bars.hide()
        self.dots = TypingDots()
        self.dots.hide()
        self.activity_label = QLabel("Ready")
        self.activity_label.setObjectName("ActivityText")
        act.addWidget(self.bars)
        act.addWidget(self.dots)
        act.addWidget(self.activity_label)
        act.addStretch(1)
        col.addLayout(act)

        # Input with inline mic + send (kept compact).
        self.input = QLineEdit()
        self.input.setObjectName("Input")
        self.input.setPlaceholderText("Ask JARVIS…")
        self.input.returnPressed.connect(self._send)
        self.input.installEventFilter(self)
        self.mic = MicButton("MicMini", icon_px=16, idle_icon="mic", active_icon="square")
        self.mic.setToolTip("Record one message")
        self.mic.clicked.connect(self.ctrl.toggle_record)

        self.input_wrap = QFrame()
        self.input_wrap.setObjectName("InputWrap")
        wrap = QHBoxLayout(self.input_wrap)
        wrap.setContentsMargins(4, 3, 6, 3)
        wrap.setSpacing(2)
        wrap.addWidget(self.input, 1)
        wrap.addWidget(self.mic)

        send = IconButton("send", color="#ffffff", hover_color="#ffffff",
                          size=18, object_name="Send", tooltip="Send")
        send.clicked.connect(self._send)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.input_wrap, 1)
        row.addWidget(send)
        col.addLayout(row)

    # --------------------------------------------------------------- theme
    def _accent(self) -> tuple[str, str]:
        return permission_accent(self.ctrl.permission_mode)

    # Slim the input for the flyout (smaller than the full orb's).
    _COMPACT = (
        "#InputWrap { border-radius: 17px; }"
        "#Input { padding: 4px 4px 4px 12px; font-size: 12px; }"
    )

    def _apply_theme(self) -> None:
        pal = theme_manager.palette()
        a, a2 = self._accent()
        self.setStyleSheet(glass_qss(pal, accent=a, accent2=a2) + self._COMPACT)
        self.mic.set_idle_color(pal.subtext)
        self.bars.set_color(a)
        self.dots.set_color(pal.subtext)
        self._render_live()

    def _render_live(self) -> None:
        on = self.live_btn.property("live") == "true"
        color = "#ffffff" if on else theme_manager.palette().subtext
        self.live_btn.setIcon(lucide_icon("audio-lines", color=color, size=14))

    # ---------------------------------------------------------------- wire
    def _wire(self) -> None:
        c = self.ctrl
        c.status_changed.connect(self._on_status)
        c.busy_changed.connect(self._on_busy)
        c.recording_changed.connect(self._on_recording)
        c.listening_changed.connect(self._set_live)
        c.permission_mode_changed.connect(self._on_mode)
        c.user_said.connect(lambda t: self._add_message("user", t))
        c.reply_started.connect(self._on_reply_started)
        c.reply_chunk.connect(self._on_reply_chunk)
        c.reply_finished.connect(self._on_reply_finished)
        c.error_occurred.connect(self._on_error)

    # ------------------------------------------------------- transcript
    def _add_message(self, role: str, text: str) -> Message:
        msg = Message(role, text)
        self.msg_lay.insertWidget(self.msg_lay.count() - 1, msg)
        self._trim()
        self._scroll_to_bottom()
        return msg

    def _trim(self) -> None:
        # Keep the last MAX_MESSAGES rows (index count-1 is the trailing stretch).
        while self.msg_lay.count() - 1 > MAX_MESSAGES:
            item = self.msg_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        # Defer one tick so the freshly-added row is laid out before we scroll.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _replay(self) -> None:
        for turn in self.ctrl.history[-6:]:
            if turn.get("role") in ("user", "assistant"):
                self._add_message(turn["role"], turn.get("content", ""))

    def _on_reply_started(self) -> None:
        self._reply_text = ""
        self._reply_msg = self._add_message("assistant", "")

    def _on_reply_chunk(self, delta: str) -> None:
        self._reply_text += delta
        if self._reply_msg is None:
            self._reply_msg = self._add_message("assistant", "")
        self._reply_msg.set_text(self._reply_text)
        self._scroll_to_bottom()

    def _on_reply_finished(self, text: str) -> None:
        if self._reply_msg is None:
            self._reply_msg = self._add_message("assistant", "")
        self._reply_msg.set_text(text or "…")
        self._reply_msg = None
        self._reply_text = ""
        self._scroll_to_bottom()

    def _on_error(self, message: str) -> None:
        uri = lucide_data_uri("alert-triangle", color="#ff8791", size=12)
        self._reply_msg = None
        self._add_message("assistant",
                          f'<img src="{uri}" width="12" height="12">&nbsp; {message}')

    # ------------------------------------------------------- activity state
    def _on_status(self, text: str) -> None:
        self._status_text = text or ""
        low = self._status_text.lower()
        self._hearing = "hear" in low
        self._tts = "speak" in low
        self._refresh_activity()

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        self.input.setEnabled(not busy)
        self._refresh_activity()

    def _on_recording(self, on: bool) -> None:
        self._recording = on
        self.mic.set_recording(on)
        self._refresh_activity()

    def _set_live(self, on: bool) -> None:
        self._live = on
        self.live_btn.setProperty("live", "true" if on else "false")
        self.live_btn.setText("  Live · on" if on else "  Live")
        self.live_btn.style().unpolish(self.live_btn)
        self.live_btn.style().polish(self.live_btn)
        self._render_live()
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        """Pick the one indicator that matches what JARVIS is doing right now."""
        user_speaking = self._recording or self._hearing
        if user_speaking:
            bars, dots, label = "active", False, "Listening to you…"
        elif self._busy:
            bars, dots, label = "off", True, (self._status_text or "Thinking…")
        elif self._tts:
            bars, dots, label = "active", False, "Speaking…"
        elif self._live:
            bars, dots, label = "calm", False, "Live · listening"
        else:
            bars, dots, label = "off", False, (self._status_text or "Ready")

        self.bars.set_mode(bars)
        self.bars.setVisible(bars != "off")
        self.dots.setVisible(dots)
        self.dots.start() if dots else self.dots.stop()
        self.activity_label.setText(label)

    def _on_mode(self, mode: str) -> None:
        want = mode.capitalize()
        if self.mode_combo.currentText() != want:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentText(want)
            self.mode_combo.blockSignals(False)
        self._apply_theme()

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.ctrl.send_text(text)

    def eventFilter(self, obj, event):  # noqa: ANN001
        if obj is self.input and event.type() in (
                QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            focused = event.type() == QEvent.Type.FocusIn
            self.input_wrap.setProperty("focused", "true" if focused else "false")
            self.input_wrap.style().unpolish(self.input_wrap)
            self.input_wrap.style().polish(self.input_wrap)
        return super().eventFilter(obj, event)

    # -------------------------------------------------------------- show
    def hideEvent(self, event) -> None:  # noqa: ANN001
        # Park animations while the flyout isn't visible.
        self.bars.set_mode("off")
        self.dots.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._refresh_activity()

    def show_above_tray(self) -> None:
        """Dock the flyout at the bottom-right, just above the taskbar tray."""
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - MARGIN,
                  screen.bottom() - self.height() - MARGIN)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
