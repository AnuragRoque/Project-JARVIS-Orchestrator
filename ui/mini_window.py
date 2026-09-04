"""The quick bar — a tiny flyout docked above the system-tray icon.

Design goals (per the product mock): **minimal height in normal mode, one item
at a time, expand only when needed.** The flyout shows a single current item —
either JARVIS *listening* (with a live waveform + stop), your *latest command*,
or JARVIS's *latest reply* (with a thinking animation) — never a scrolling
transcript. The full conversation lives in the orb / full window.

Chrome, left to right:

* Header — title, then the core surface controls: open the floating **orb**,
  open the **full window**, and **close**.
* Controls — a **Live** toggle, the **permission** pill (Auto / Partial /
  Manual), and a **keyboard** chevron that flips the input between speaking and
  typing.
* Input — voice ("Ask JARVIS…" + mic) or keyboard ("Type to JARVIS…"), plus send.

Only one surface (quick bar / orb / full window) is shown at a time — the Runner
enforces that. None of the core wiring (Live, permission mode, mic, send, orb,
full window) is changed here; this module only re-skins and re-arranges it.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
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

from jarvis.ui.icons import lucide_data_uri, lucide_icon, lucide_pixmap
from jarvis.ui.theme import dot_pixmap, glass_qss, permission_accent, theme_manager
from jarvis.ui.widgets.activity import TypingDots, WaveBars
from jarvis.ui.widgets.chat_view import MicButton
from jarvis.ui.widgets.icon_button import IconButton

WIDTH = 360
MARGIN = 8


class ListenPanel(QWidget):
    """Normal-mode 'JARVIS is listening' view: a label + prompt on the left, a
    live waveform and a round stop button on the right."""

    def __init__(self, on_stop) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 4, 2, 4)
        row.setSpacing(8)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.title = QLabel("Listening…")
        self.title.setObjectName("ListenTitle")
        self.sub = QLabel("Say something…")
        self.sub.setObjectName("ListenSub")
        texts.addWidget(self.title)
        texts.addWidget(self.sub)
        row.addLayout(texts)
        row.addStretch(1)

        self.bars = WaveBars(bars=7)
        self.bars.setMinimumWidth(60)
        row.addWidget(self.bars)

        self.stop = IconButton("square", color="#ffffff", hover_color="#ffffff",
                               size=15, object_name="StopBtn", tooltip="Stop listening")
        self.stop.clicked.connect(on_stop)
        row.addWidget(self.stop)

    def set_speaking(self, speaking: bool) -> None:
        self.bars.set_mode("active" if speaking else "calm")
        self.sub.setText("Go ahead — I'm hearing you…" if speaking else "Say something…")


class MessagePanel(QWidget):
    """Normal-mode single message: a role marker (icon + name) with an optional
    thinking animation, over a word-wrapped body that scrolls if it runs long."""

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        col = QVBoxLayout(self)
        col.setContentsMargins(2, 4, 2, 4)
        col.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(7)
        self.icon = QLabel()
        self.name = QLabel("JARVIS")
        self.name.setObjectName("RoleName")
        self.dots = TypingDots()
        self.dots.hide()
        head.addWidget(self.icon)
        head.addWidget(self.name)
        head.addWidget(self.dots)
        head.addStretch(1)
        col.addLayout(head)

        # Body hugs its content, scrolling (bar hidden) only past a capped height.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Chat")
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        self.body = QLabel("")
        self.body.setObjectName("MsgBody")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hl.addWidget(self.body)
        self.scroll.setWidget(host)
        col.addWidget(self.scroll)

    _BODY_W = 300     # wrap width (window is fixed at WIDTH); used to size the body
    _BODY_CAP = 150   # tallest the body grows before it starts scrolling

    def _fit_body(self) -> None:
        h = self.body.heightForWidth(self._BODY_W)
        if h < 0:
            h = self.body.sizeHint().height()
        self.scroll.setFixedHeight(max(18, min(self._BODY_CAP, h + 2)))

    def set_message(self, role: str, text: str, accent: str,
                    subcolor: str, thinking: bool = False) -> None:
        icon_name = "user" if role == "user" else "audio-lines"
        self.icon.setPixmap(lucide_pixmap(icon_name, color=accent, size=15))
        self.name.setText("You" if role == "user" else "JARVIS")
        self.name.setStyleSheet(f"color: {accent};")
        self.body.setText(text)
        self.body.setVisible(bool(text))
        self._fit_body()
        self.dots.setVisible(thinking)
        if thinking:
            self.dots.set_color(subcolor)
            self.dots.start()
        else:
            self.dots.stop()
        # newest content at the top-left is already visible; reset scroll
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))


class MiniBar(QWidget):
    request_floating = pyqtSignal()
    request_maximise = pyqtSignal()

    def __init__(self, controller) -> None:
        super().__init__()
        self.ctrl = controller

        # what to show in normal mode (one item at a time)
        self._page = ""                 # "listen" | "message"
        self._reply_text = ""
        self._replying = False
        self._awaiting_reply = False
        self._keyboard = False

        # activity flags
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
        self._apply_input_mode()
        self._wire()
        self._show_initial()
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
        col.setSpacing(9)

        # Header: title + the three core surface controls (unchanged behaviour).
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

        # Controls: Live · permission pill · keyboard chevron. All fixed-size so
        # toggling any label can never reflow into a neighbour.
        ctrls = QHBoxLayout()
        ctrls.setSpacing(8)
        self.live_btn = QPushButton("  Live")
        self.live_btn.setObjectName("LiveToggle")
        self.live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_btn.setToolTip("Live hands-free conversation on/off")
        self.live_btn.setFixedSize(96, 30)
        self.live_btn.clicked.connect(self.ctrl.toggle_live)
        ctrls.addWidget(self.live_btn)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModePill")
        self.mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_combo.setToolTip(
            "Auto: run everything · Partial: ask before risky actions · "
            "Manual: ask before anything but read-only")
        self.mode_combo.setFixedSize(104, 30)
        for label in ("Auto", "Partial", "Manual"):
            accent, _ = permission_accent(label.lower())
            self.mode_combo.addItem(QIcon(dot_pixmap(accent, 11)), label)
        self.mode_combo.setCurrentText(self.ctrl.permission_mode.capitalize())
        self.mode_combo.currentTextChanged.connect(
            lambda t: self.ctrl.set_permission_mode(t.lower()))
        ctrls.addWidget(self.mode_combo)

        self.kbd_btn = IconButton("chevron-down", size=15, object_name="KbdToggle",
                                  tooltip="Type instead of speak")
        self.kbd_btn.setFixedSize(40, 30)
        self.kbd_btn.clicked.connect(self._toggle_keyboard)
        ctrls.addWidget(self.kbd_btn)
        ctrls.addStretch(1)
        col.addLayout(ctrls)

        # Content: exactly one of these is shown at a time.
        self.listen_panel = ListenPanel(on_stop=self.ctrl.toggle_live)
        self.msg_panel = MessagePanel()
        self.listen_panel.hide()
        self.msg_panel.hide()
        col.addWidget(self.listen_panel)
        col.addWidget(self.msg_panel)

        # Input: voice or keyboard, with an inline mic + round send.
        self.input = QLineEdit()
        self.input.setObjectName("Input")
        self.input.returnPressed.connect(self._send)
        self.input.installEventFilter(self)

        self.kbd_hint = QLabel()
        self.kbd_hint.setObjectName("KbdHint")
        self.kbd_hint.hide()

        self.mic = MicButton("MicMini", icon_px=16, idle_icon="mic", active_icon="square")
        self.mic.setToolTip("Record one message")
        self.mic.clicked.connect(self.ctrl.toggle_record)

        self.input_wrap = QFrame()
        self.input_wrap.setObjectName("InputWrap")
        wrap = QHBoxLayout(self.input_wrap)
        wrap.setContentsMargins(4, 3, 6, 3)
        wrap.setSpacing(2)
        wrap.addWidget(self.kbd_hint)
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

    _COMPACT = (
        "#InputWrap { border-radius: 17px; }"
        "#Input { padding: 4px 4px 4px 10px; font-size: 12px; }"
    )

    def _apply_theme(self) -> None:
        pal = theme_manager.palette()
        a, a2 = self._accent()
        self.setStyleSheet(glass_qss(pal, accent=a, accent2=a2) + self._COMPACT)
        self.mic.set_idle_color(pal.subtext)
        self.listen_panel.bars.set_color(a)
        self._render_live()
        self._render_kbd()
        self.kbd_hint.setPixmap(lucide_pixmap("keyboard", color=pal.subtext, size=15))

    def _render_live(self) -> None:
        on = self.live_btn.property("live") == "true"
        a, _ = self._accent()
        color = a if on else theme_manager.palette().subtext
        self.live_btn.setIcon(lucide_icon("audio-lines", color=color, size=14))

    def _render_kbd(self) -> None:
        a, _ = self._accent()
        pal = theme_manager.palette()
        name = "keyboard" if self._keyboard else "chevron-down"
        color = a if self._keyboard else pal.subtext
        self.kbd_btn.set_colors(color, a)
        self.kbd_btn._name = name           # swap glyph
        self.kbd_btn._render(color)

    # ---------------------------------------------------------------- wire
    def _wire(self) -> None:
        c = self.ctrl
        c.status_changed.connect(self._on_status)
        c.busy_changed.connect(self._on_busy)
        c.recording_changed.connect(self._on_recording)
        c.listening_changed.connect(self._set_live)
        c.permission_mode_changed.connect(self._on_mode)
        c.user_said.connect(self._on_user_said)
        c.reply_started.connect(self._on_reply_started)
        c.reply_chunk.connect(self._on_reply_chunk)
        c.reply_finished.connect(self._on_reply_finished)
        c.error_occurred.connect(self._on_error)

    # ------------------------------------------------------- input mode
    def _toggle_keyboard(self) -> None:
        self._keyboard = not self._keyboard
        self._apply_input_mode()

    def _apply_input_mode(self) -> None:
        self.input.setPlaceholderText("Type to JARVIS…" if self._keyboard else "Ask JARVIS…")
        self.kbd_hint.setVisible(self._keyboard)
        self.kbd_btn.setProperty("active", "true" if self._keyboard else "false")
        self.kbd_btn.style().unpolish(self.kbd_btn)
        self.kbd_btn.style().polish(self.kbd_btn)
        self._render_kbd()
        if self._keyboard:
            self.input.setFocus()

    # ------------------------------------------------------- current item
    def _set_page(self, page: str) -> None:
        self._page = page
        self.listen_panel.setVisible(page == "listen")
        self.msg_panel.setVisible(page == "message")

    def _show_message(self, role: str, text: str, thinking: bool = False) -> None:
        a, _ = self._accent()
        sub = theme_manager.palette().subtext
        self.msg_panel.set_message(role, text, accent=a, subcolor=sub, thinking=thinking)
        self._set_page("message")
        self._relayout()

    def _show_listen(self) -> None:
        self.listen_panel.set_speaking(self._recording or self._hearing)
        self._set_page("listen")
        self._relayout()

    def _show_initial(self) -> None:
        last = None
        for turn in reversed(self.ctrl.history):
            if turn.get("role") in ("user", "assistant"):
                last = turn
                break
        if last is not None:
            role = "user" if last["role"] == "user" else "assistant"
            self._show_message(role, last.get("content", ""))
        else:
            self._show_message("assistant", "Hi — ask me anything, or tap Live to talk.")

    # ------------------------------------------------ controller signals
    def _on_user_said(self, text: str) -> None:
        # Show your command (state 3) for a beat, then hand off to the thinking
        # animation (state 4) if JARVIS hasn't started replying yet.
        self._replying = False
        self._reply_text = ""
        self._awaiting_reply = True
        self._show_message("user", text)
        QTimer.singleShot(700, self._maybe_thinking)

    def _maybe_thinking(self) -> None:
        if self._awaiting_reply and not self._reply_text and not self._replying:
            self._show_message("assistant", "", thinking=True)

    def _on_reply_started(self) -> None:
        self._reply_text = ""
        self._replying = True
        self._show_message("assistant", "", thinking=True)

    def _on_reply_chunk(self, delta: str) -> None:
        self._reply_text += delta
        self._show_message("assistant", self._reply_text, thinking=False)

    def _on_reply_finished(self, text: str) -> None:
        self._replying = False
        self._awaiting_reply = False
        self._show_message("assistant", text or "…", thinking=False)

    def _on_error(self, message: str) -> None:
        self._replying = False
        self._awaiting_reply = False
        uri = lucide_data_uri("alert-triangle", color="#ff8791", size=12)
        self._show_message("assistant",
                           f'<img src="{uri}" width="12" height="12">&nbsp; {message}')

    def _on_status(self, text: str) -> None:
        self._status_text = text or ""
        low = self._status_text.lower()
        self._hearing = "hear" in low
        self._tts = "speak" in low
        self._refresh_view()

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        self.input.setEnabled(not busy)
        self._refresh_view()

    def _on_recording(self, on: bool) -> None:
        self._recording = on
        self.mic.set_recording(on)
        self._refresh_view()

    def _set_live(self, on: bool) -> None:
        self._live = on
        self.live_btn.setProperty("live", "true" if on else "false")
        self.live_btn.style().unpolish(self.live_btn)
        self.live_btn.style().polish(self.live_btn)
        self._render_live()
        self._refresh_view()

    def _refresh_view(self) -> None:
        """Pick the single item to show now. Explicit message events (you / reply)
        drive the message panel; this handles the listening panel and idle."""
        # Actively capturing your voice → the listening panel.
        if self._recording or self._hearing:
            self._show_listen()
            return
        # Live and quietly waiting (not mid-reply) → the listening panel.
        if (self._live and not self._busy and not self._tts and not self._awaiting_reply
                and "listen" in self._status_text.lower()):
            self._show_listen()
            return
        # Otherwise leave whatever message is already shown (or seed one).
        if self._page == "":
            self._show_initial()

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
        self.listen_panel.bars.set_mode("off")
        self.msg_panel.dots.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._refresh_view()

    def _fit(self) -> None:
        """Resize height to the current content. We size from the *card* directly:
        the card's drop-shadow effect breaks size-hint propagation to the window,
        so ``self.sizeHint()`` under-reports and ``adjustSize()`` misbehaves. The
        inner layouts are invalidated first so the card hint is fresh *now* rather
        than after the next event loop (a resize-fixed child only posts its layout
        request; without this the flyout would lag a frame behind long replies)."""
        for w in (self.msg_panel, self.listen_panel, self.card):
            lay = w.layout()
            if lay is not None:
                lay.invalidate()
                lay.activate()
        m = self.layout().contentsMargins()
        h = self.card.sizeHint().height() + m.top() + m.bottom()
        # setFixedHeight (not resize): the graphics effect also corrupts the
        # window's minimumSizeHint, which would otherwise clamp a shrink.
        self.setFixedHeight(h)

    def _relayout(self) -> None:
        """Fit to the current content and keep the BOTTOM edge pinned above the
        tray, so a long reply grows the flyout upward instead of pushing its
        input off the bottom of the screen."""
        self._fit()
        if not self.isVisible():
            return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - MARGIN,
                  screen.bottom() - self.height() - MARGIN)

    def show_above_tray(self) -> None:
        """Dock the flyout at the bottom-right, just above the taskbar tray."""
        self._fit()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - MARGIN,
                  screen.bottom() - self.height() - MARGIN)
        self.show()
        self.raise_()
        self.activateWindow()
        if self._keyboard:
            self.input.setFocus()
        else:
            self.input.clearFocus()
