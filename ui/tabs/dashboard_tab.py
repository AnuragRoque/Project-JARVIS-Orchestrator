"""Tab 6 — Dashboard (early preview).

A live at-a-glance view: power state, active reminders, activity captured, and the
most recent actions JARVIS took. Marked a preview — the full dashboard (usage
charts, trends) lands later — but these cards already read real data so the layout
is the intended one, not an empty stub.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

_CARD_STYLE = """
#DashCard { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px; }
#DashCardTitle { color: #8aa0c6; font-size: 12px; font-weight: 600;
                 letter-spacing: 1px; }
#DashBig { color: #eaf0ff; font-size: 30px; font-weight: 700; }
#DashBody { color: #c3ccdd; font-size: 13px; }
#DashHeader { color: #eaf0ff; font-size: 22px; font-weight: 700; }
#DashBadge { color: #0b1220; background: #6ea8ff; border-radius: 8px;
             padding: 2px 10px; font-size: 11px; font-weight: 700; }
"""


class _Card(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("DashCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        t = QLabel(title.upper())
        t.setObjectName("DashCardTitle")
        lay.addWidget(t)
        self.big = QLabel("—")
        self.big.setObjectName("DashBig")
        lay.addWidget(self.big)
        self.body = QLabel("")
        self.body.setObjectName("DashBody")
        self.body.setWordWrap(True)
        lay.addWidget(self.body)
        lay.addStretch(1)

    def set(self, big: str, body: str = "") -> None:
        self.big.setText(big)
        self.body.setText(body)


class DashboardTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_CARD_STYLE)
        self._build()
        self._refresh()
        from jarvis.app.safety import guard
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(guard(self._maybe_refresh, where="dashboard-refresh"))
        self._timer.start()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(16)

        head = QHBoxLayout()
        h = QLabel("Dashboard")
        h.setObjectName("DashHeader")
        head.addWidget(h)
        badge = QLabel("PREVIEW")
        badge.setObjectName("DashBadge")
        head.addWidget(badge)
        head.addStretch(1)
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.card_power = _Card("Power")
        self.card_reminders = _Card("Active reminders")
        self.card_activity = _Card("Activity captured")
        self.card_actions = _Card("Recent actions")
        grid.addWidget(self.card_power, 0, 0)
        grid.addWidget(self.card_reminders, 0, 1)
        grid.addWidget(self.card_activity, 1, 0)
        grid.addWidget(self.card_actions, 1, 1)
        lay.addLayout(grid, 1)

    # -------------------------------------------------------------- refresh
    def _maybe_refresh(self) -> None:
        if self.isVisible():
            self._refresh()

    def _refresh(self) -> None:
        self._refresh_power()
        self._refresh_reminders()
        self._refresh_activity()
        self._refresh_actions()

    def _refresh_power(self) -> None:
        try:
            from jarvis.modules.power.status import get_status
            s = get_status()
            if s.get("has_battery"):
                self.card_power.set(f"{s.get('percent','?')}%", s.get("summary", ""))
            else:
                self.card_power.set("AC", s.get("summary", ""))
        except Exception:
            self.card_power.set("—", "Unavailable")

    def _refresh_reminders(self) -> None:
        try:
            from jarvis.modules.reminders.store import ReminderStore
            rows = ReminderStore().pending()
            top = rows[0]["text"] if rows else ""
            self.card_reminders.set(str(len(rows)),
                                    f"Next: {top}" if top else "None pending")
        except Exception:
            self.card_reminders.set("—", "Unavailable")

    def _refresh_activity(self) -> None:
        try:
            from jarvis.modules.timeline.recall.storage import get_repository
            c = get_repository().counts()
            self.card_activity.set(
                str(c.get("sessions", 0)),
                f"{c.get('browser_visits',0)} pages · {c.get('file_events',0)} files")
        except Exception:
            self.card_activity.set("—", "Unavailable")

    def _refresh_actions(self) -> None:
        try:
            from jarvis.app.eventlog import recent_events
            evs = recent_events(limit=5)
            self.card_actions.set(
                str(len(evs)),
                "\n".join(f"• {e.get('summary','')[:60]}" for e in evs) or "No actions yet")
        except Exception:
            self.card_actions.set("—", "Unavailable")
