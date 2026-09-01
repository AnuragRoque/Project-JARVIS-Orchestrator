"""Tab 4 — Logs: a searchable, filterable view of everything JARVIS did.

Reads the structured ``event_log`` (tool calls, arguments, results, and each
permission decision). Full-text search (FTS5) + module / decision filters; click a
row to see its full detail. Auto-refreshes while idle so new actions appear live,
but pauses the refresh while you're reading a selected row or typing a search.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.app.eventlog import distinct_modules, search_events
from jarvis.app.safety import guard

_COLUMNS = ["Time", "Module", "Summary", "Risk", "Decision"]
_DECISIONS = ["All decisions", "said", "answered", "allowed", "declined",
              "confirmed", "executed", "scheduled", "fired"]


class LogsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._build()
        self._reload_filters()
        self._reload()

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(guard(self._maybe_auto_refresh, where="logs-refresh"))
        self._timer.start()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search commands, tools, results…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._reload)
        bar.addWidget(self.search, 1)

        self.module_filter = QComboBox()
        self.module_filter.currentIndexChanged.connect(self._reload)
        bar.addWidget(self.module_filter)

        self.decision_filter = QComboBox()
        self.decision_filter.addItems(_DECISIONS)
        self.decision_filter.currentIndexChanged.connect(self._reload)
        bar.addWidget(self.decision_filter)

        refresh = QPushButton("Refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self._manual_refresh)
        bar.addWidget(refresh)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Summary
        for c in (0, 1, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._show_detail)
        lay.addWidget(self.table, 3)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Subtitle")
        lay.addWidget(self.count_label)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Select a row to see the full detail…")
        self.detail.setMaximumHeight(150)
        lay.addWidget(self.detail, 1)

    # -------------------------------------------------------------- loading
    def _reload_filters(self) -> None:
        current = self.module_filter.currentText() if self.module_filter.count() else ""
        self.module_filter.blockSignals(True)
        self.module_filter.clear()
        self.module_filter.addItem("All modules")
        self.module_filter.addItems(distinct_modules())
        idx = self.module_filter.findText(current)
        if idx >= 0:
            self.module_filter.setCurrentIndex(idx)
        self.module_filter.blockSignals(False)

    def _manual_refresh(self) -> None:
        self._reload_filters()
        self._reload()

    def _maybe_auto_refresh(self) -> None:
        # Don't yank the view while the user is searching or inspecting a row.
        if not self.isVisible():
            return
        if self.search.text().strip() or self.table.selectedItems():
            return
        self._reload()

    def _reload(self) -> None:
        module = self.module_filter.currentText()
        module = None if (not module or module == "All modules") else module
        decision = self.decision_filter.currentText()
        decision = None if decision == "All decisions" else decision

        self._rows = search_events(
            self.search.text().strip(), module=module, decision=decision, limit=500)
        self._populate()

    def _populate(self) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._rows))
        for r, ev in enumerate(self._rows):
            cells = [
                _time(ev.get("ts", "")),
                ev.get("module", ""),
                ev.get("summary", ""),
                ev.get("risk", ""),
                ev.get("decision", ""),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 4:  # decision colour
                    col = _decision_color(text)
                    if col:
                        item.setForeground(col)
                self.table.setItem(r, c, item)
        self.table.setUpdatesEnabled(True)
        self.count_label.setText(f"{len(self._rows)} event(s)")

    def _show_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        ev = self._rows[rows[0].row()]
        lines = [
            f"Time:     {ev.get('ts','')}",
            f"Kind:     {ev.get('kind','')}",
            f"Module:   {ev.get('module','')}",
            f"Risk:     {ev.get('risk','')}",
            f"Decision: {ev.get('decision','')}",
            "",
            f"Summary:  {ev.get('summary','')}",
            "",
            "Detail:",
            ev.get("detail", "") or "(none)",
        ]
        self.detail.setPlainText("\n".join(lines))


def _time(ts: str) -> str:
    # "2026-08-28T05:59:41" -> "08-28 05:59:41"
    return ts.replace("T", "  ")[5:] if "T" in ts else ts


def _decision_color(decision: str) -> QColor | None:
    d = (decision or "").lower()
    if d in ("said", "answered"):          # conversation turns
        return QColor(120, 170, 255)
    if d.startswith("declined"):
        return QColor(255, 107, 122)
    if "confirmed" in d or d.startswith("allowed") or d in ("executed", "opened"):
        return QColor(120, 200, 140)
    return None
