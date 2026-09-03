"""The collapsed floating orb — an audio-reactive, state-aware 'J' badge.

It paints itself (radial-gradient sphere + monogram) and, when JARVIS is doing
something, animates a soft pulse ring:

* **idle**       — still, no ring
* **listening**  — slow calm pulse
* **thinking**   — quick pulse
* **speaking**   — medium pulse

Its colour is the *permission accent* (blue Manual / amber Partial / red Auto),
set from outside via :meth:`set_accent`, so the orb itself signals the current
"mood". It is transparent to the mouse so the parent window still owns drag/tap.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

_DURATION = {"listening": 1500, "thinking": 700, "speaking": 1100}


class Orb(QWidget):
    def __init__(self, diameter: int = 68, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._accent = QColor("#2f9bff")
        self._accent2 = QColor("#0e63ff")
        self._state = "idle"
        self._pulse = 0.0
        self._anim = QPropertyAnimation(self, b"pulse")
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1500)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    # animated property -----------------------------------------------------
    def get_pulse(self) -> float:
        return self._pulse

    def set_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    pulse = pyqtProperty(float, fget=get_pulse, fset=set_pulse)

    # public API -------------------------------------------------------------
    def set_accent(self, accent: str, accent2: str) -> None:
        self._accent = QColor(accent)
        self._accent2 = QColor(accent2)
        self.update()

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        if state == "idle":
            self._anim.stop()
            self.set_pulse(0.0)
        else:
            self._anim.setDuration(_DURATION.get(state, 1300))
            if self._anim.state() != QPropertyAnimation.State.Running:
                self._anim.start()
        self.update()

    # painting ---------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        base_r = self._d / 2 - 8

        if self._state != "idle":
            ring = QColor(self._accent)
            ring.setAlphaF(0.32 * (1.0 - self._pulse))
            radius = base_r + 2 + self._pulse * 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            p.drawEllipse(center, int(radius), int(radius))

        grad = QRadialGradient(center.x(), center.y() - base_r * 0.2, base_r * 1.25)
        grad.setColorAt(0.0, self._accent.lighter(140))
        grad.setColorAt(1.0, self._accent2)
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, int(base_r), int(base_r))

        p.setPen(QColor("#ffffff"))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(int(base_r))
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "J")
        p.end()
