"""The floating orb: a frameless, always-on-top compact hub.

It shares the app's single :class:`VoiceController`, so it can take voice/text
and execute everything on its own. The maximise button opens the full tabbed
window; it collapses to a live, audio-reactive orb and can be dragged anywhere.

Two things colour it: the **global theme** (background/panel/text) and the
**permission accent** — blue Manual / amber Partial / red Auto — which tints the
orb, mic and highlights so the window itself signals how much autonomy JARVIS
currently has.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from jarvis.app.config.settings import get_settings
from jarvis.app.logsetup import get_logger
from jarvis.ui.theme import glass_qss, permission_accent, theme_manager
from jarvis.ui.widgets.chat_view import ChatView
from jarvis.ui.widgets.icon_button import IconButton
from jarvis.ui.widgets.orb import Orb

log = get_logger("floating")

CARD_W, CARD_H = 400, 600
CARD_MIN_W, CARD_MIN_H = 320, 440
ORB_WIN = 92          # window size while collapsed
DIM_OPACITY = 0.90


class FloatingWindow(QWidget):
    request_maximise = pyqtSignal()

    def __init__(self, controller) -> None:
        super().__init__()
        self.ctrl = controller
        self._drag_pos: QPoint | None = None
        self._press_global: QPoint | None = None
        self._moved = False
        self._collapsed = False

        # live state (drives the orb)
        self._live = False
        self._busy = False
        self._speaking = False

        gs = get_settings()
        size = gs.get("float_size") or [CARD_W, CARD_H]
        self._card_w = int(size[0]) if size else CARD_W
        self._card_h = int(size[1]) if size else CARD_H
        self._dim = bool(gs.get("dim_when_idle", True))

        self.setWindowTitle("JARVIS")
        self.setMinimumSize(CARD_MIN_W, CARD_MIN_H)
        self.resize(self._card_w, self._card_h)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build()
        self._apply_theme()
        self._wire_state()
        theme_manager.changed.connect(self._apply_theme)

        self._restore_position()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        self.card = QWidget()
        self.card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(blurRadius=40, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        # Collapsed state: the audio-reactive orb (transparent to the mouse; the
        # window owns drag + tap-to-expand).
        self.orb = Orb(68)
        self.orb.hide()
        outer.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(16, 14, 16, 10)
        card_lay.setSpacing(8)

        # Title bar with window controls
        bar = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("JARVIS")
        title.setObjectName("Title")
        sub = QLabel("assistant")
        sub.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(sub)
        bar.addLayout(titles)
        bar.addStretch()

        self.btn_max = IconButton("maximize-2", size=15, tooltip="Open the full window")
        self.btn_max.clicked.connect(self.request_maximise.emit)
        self.btn_min = IconButton("minus", size=15, tooltip="Collapse to orb")
        self.btn_min.clicked.connect(self._collapse)
        self.btn_close = IconButton("x", size=15, tooltip="Hide (stays in the tray)",
                                    hover_color="#ff6b7a")
        self.btn_close.clicked.connect(self.hide)
        for b in (self.btn_max, self.btn_min, self.btn_close):
            bar.addWidget(b)
        card_lay.addLayout(bar)

        self.view = ChatView(self.ctrl, compact=True)
        card_lay.addWidget(self.view, 1)

        # Resize grip, tucked in the card's bottom-right corner.
        self.grip = QSizeGrip(self.card)
        self.grip.resize(14, 14)

    # --------------------------------------------------------------- theme
    def _accent(self) -> tuple[str, str]:
        return permission_accent(self.ctrl.permission_mode)

    def _apply_theme(self) -> None:
        a, a2 = self._accent()
        self.setStyleSheet(glass_qss(theme_manager.palette(), accent=a, accent2=a2))
        self.orb.set_accent(a, a2)

    # --------------------------------------------------- live state → orb
    def _wire_state(self) -> None:
        c = self.ctrl
        c.listening_changed.connect(self._on_listening)
        c.busy_changed.connect(self._on_busy)
        c.status_changed.connect(self._on_status)
        c.permission_mode_changed.connect(lambda _m: self._apply_theme())

    def _on_listening(self, live: bool) -> None:
        self._live = live
        self._refresh_orb()

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        if not busy:
            self._speaking = False
        self._refresh_orb()

    def _on_status(self, text: str) -> None:
        self._speaking = "speak" in (text or "").lower()
        self._refresh_orb()

    def _refresh_orb(self) -> None:
        if self._speaking:
            state = "speaking"
        elif self._busy:
            state = "thinking"
        elif self._live:
            state = "listening"
        else:
            state = "idle"
        self.orb.set_state(state)

    # --------------------------------------------------------------- layout
    def _restore_position(self) -> None:
        pos = get_settings().get("float_pos")
        screen = QApplication.primaryScreen().availableGeometry()
        if pos and len(pos) == 2:
            x = max(screen.left(), min(int(pos[0]), screen.right() - self.width()))
            y = max(screen.top(), min(int(pos[1]), screen.bottom() - self.height()))
            self.move(x, y)
        else:
            self.move(screen.right() - self.width() - 30, screen.top() + 40)

    def _persist_geometry(self) -> None:
        gs = get_settings()
        gs.set("float_pos", [self.x(), self.y()])
        if not self._collapsed:
            gs.set("float_size", [self.width(), self.height()])

    def _collapse(self) -> None:
        self._card_w, self._card_h = self.width(), self.height()
        self._collapsed = True
        self.card.hide()
        self.orb.show()
        self.setFixedSize(ORB_WIN, ORB_WIN)

    def _expand(self) -> None:
        self._collapsed = False
        self.orb.hide()
        self.setMinimumSize(CARD_MIN_W, CARD_MIN_H)
        self.setMaximumSize(16777215, 16777215)
        self.resize(self._card_w, self._card_h)
        self.card.show()

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        if hasattr(self, "grip") and not self._collapsed:
            self.grip.move(self.card.width() - self.grip.width() - 4,
                           self.card.height() - self.grip.height() - 4)

    # ------------------------------------------------------ dim when idle
    def enterEvent(self, event) -> None:  # noqa: ANN001
        self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        # Defer: opening a dropdown/menu fires leaveEvent even though we're still
        # interacting, so re-check on a short delay before dimming.
        QTimer.singleShot(150, self._maybe_dim)
        super().leaveEvent(event)

    def _maybe_dim(self) -> None:
        if not get_settings().get("dim_when_idle", True):
            return
        if self.underMouse() or QApplication.activePopupWidget() is not None:
            return  # a popup (e.g. the mode dropdown) is open — keep full opacity
        self.setWindowOpacity(DIM_OPACITY)

    # ----------------------------------------------------------- drag / tap
    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_pos = self._press_global - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint()
            if (pos - self._press_global).manhattanLength() > 4:
                self._moved = True
            self.move(pos - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        was_tap = not self._moved
        self._drag_pos = None
        if self._collapsed and was_tap:
            self._expand()
        elif self._moved:
            self._persist_geometry()   # remember where you left it (no snapping)
