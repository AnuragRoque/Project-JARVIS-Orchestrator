"""Tiny animated activity indicators for the compact quick-bar.

* :class:`WaveBars` — an equalizer-style row of bars. It eases between three
  moods: **off** (flat, animation stopped), **calm** (gentle — live mode is
  listening) and **active** (lively — you're speaking, or JARVIS is talking).
* :class:`TypingDots` — three dots that pulse in sequence while JARVIS is
  thinking; embedded in the assistant message as a placeholder.

Each is driven by a single looping ``phase`` property, so they cost nothing
while stopped and never spawn a QTimer of their own.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

_TARGET = {"off": 0.0, "calm": 0.45, "active": 1.0}


class WaveBars(QWidget):
    def __init__(self, bars: int = 5, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._n = bars
        self._phase = 0.0
        self._amp = 0.0          # eased current amplitude
        self._target = 0.0       # amplitude we're easing toward
        self._color = QColor("#ffffff")
        self.setFixedHeight(16)
        self.setMinimumWidth(bars * 6)
        self._anim = QPropertyAnimation(self, b"phase")
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(950)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)

    # animated phase ---------------------------------------------------------
    def get_phase(self) -> float:
        return self._phase

    def set_phase(self, v: float) -> None:
        self._phase = v
        self._amp += (self._target - self._amp) * 0.18   # smooth ramp in/out
        if self._target == 0.0 and self._amp < 0.03:
            self._amp = 0.0
            self._anim.stop()
        self.update()

    phase = pyqtProperty(float, fget=get_phase, fset=set_phase)

    # public -----------------------------------------------------------------
    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_mode(self, mode: str) -> None:
        self._target = _TARGET.get(mode, 0.0)
        if self._target > 0.0 and self._anim.state() != QPropertyAnimation.State.Running:
            self._anim.start()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bw = 3.0
        gap = (w - self._n * bw) / (self._n + 1)
        mid = h / 2
        for i in range(self._n):
            osc = 0.5 + 0.5 * math.sin(2 * math.pi * self._phase + i * 0.95)
            bh = 3 + osc * self._amp * (h - 4)
            x = gap + i * (bw + gap)
            col = QColor(self._color)
            col.setAlphaF(0.30 + 0.60 * min(1.0, self._amp + 0.1))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(int(x), int(mid - bh / 2), int(bw), int(bh), 1.5, 1.5)
        p.end()


class TypingDots(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._color = QColor("#8a93a3")
        self.setFixedSize(30, 14)
        self._anim = QPropertyAnimation(self, b"phase")
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1050)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)

    def get_phase(self) -> float:
        return self._phase

    def set_phase(self, v: float) -> None:
        self._phase = v
        self.update()

    phase = pyqtProperty(float, fget=get_phase, fset=set_phase)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def start(self) -> None:
        if self._anim.state() != QPropertyAnimation.State.Running:
            self._anim.start()

    def stop(self) -> None:
        self._anim.stop()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 3
        cy = self.height() / 2
        for i in range(3):
            a = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(2 * math.pi * self._phase + i * 1.1))
            col = QColor(self._color)
            col.setAlphaF(a)
            cx = 6 + i * 9
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(int(cx - r), int(cy - r), 2 * r, 2 * r)
        p.end()
