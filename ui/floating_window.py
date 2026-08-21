"""The floating orb: a frameless, always-on-top compact hub.

It shares the app's single :class:`VoiceController`, so it can take voice/text
and execute everything on its own. The maximise button opens the full tabbed
window. Collapses to a small orb; drag anywhere to move.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.styles import VOICE_STYLE
from jarvis.ui.widgets.chat_view import ChatView

CARD_W, CARD_H = 380, 560
ORB = 92


class FloatingWindow(QWidget):
    request_maximise = pyqtSignal()

    def __init__(self, controller) -> None:
        super().__init__()
        self.ctrl = controller
        self._drag_pos: QPoint | None = None
        self._press_global: QPoint | None = None
        self._moved = False
        self._collapsed = False

        self.setWindowTitle("JARVIS")
        self.setFixedSize(CARD_W, CARD_H)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(VOICE_STYLE)

        self._build()
        self._center_top_right()

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

        self.orb = QWidget()
        self.orb.setObjectName("Orb")
        self.orb.setFixedSize(68, 68)
        glow = QGraphicsDropShadowEffect(blurRadius=34, xOffset=0, yOffset=6)
        glow.setColor(QColor(43, 130, 255, 170))
        self.orb.setGraphicsEffect(glow)
        orb_lay = QVBoxLayout(self.orb)
        orb_lay.setContentsMargins(0, 0, 0, 0)
        mark = QLabel("J")
        mark.setObjectName("OrbMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb_lay.addWidget(mark)
        self.orb.hide()
        outer.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(16, 14, 16, 8)
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

        maximise = QPushButton("☐")  # ☐ maximise → open full app
        maximise.setObjectName("WinBtn")
        maximise.setToolTip("Open the full window")
        maximise.setCursor(Qt.CursorShape.PointingHandCursor)
        maximise.clicked.connect(self.request_maximise.emit)
        mini = QPushButton("–")       # – collapse to orb
        mini.setObjectName("WinBtn")
        mini.setCursor(Qt.CursorShape.PointingHandCursor)
        mini.clicked.connect(self._collapse)
        close = QPushButton("✕")      # ✕ hide (tray keeps app alive)
        close.setObjectName("WinBtn")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        for b in (maximise, mini, close):
            bar.addWidget(b)
        card_lay.addLayout(bar)

        self.view = ChatView(self.ctrl, compact=True)
        card_lay.addWidget(self.view, 1)

    # --------------------------------------------------------------- layout
    def _center_top_right(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 30, screen.top() + 40)

    def _collapse(self) -> None:
        self._collapsed = True
        self.card.hide()
        self.orb.show()
        self.setFixedSize(ORB, ORB)

    def _expand(self) -> None:
        self._collapsed = False
        self.orb.hide()
        self.setFixedSize(CARD_W, CARD_H)
        self.card.show()

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

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
