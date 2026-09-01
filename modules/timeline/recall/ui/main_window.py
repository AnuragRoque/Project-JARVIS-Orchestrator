"""Main application window: sidebar navigation, search, and results."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

from ..config import get_config
from ..logging_setup import get_logger
from ..resource import OpenError, open_result
from ..search import get_search_engine
from ..storage import get_repository
from .result_item import make_result_widget, format_duration
from .settings_page import SettingsPage
from .workers import SearchWorker, SemanticBuildWorker

log = get_logger("ui.window")

# Sidebar sections -> internal id.
SECTIONS = [
    ("Today", "today"),
    ("Yesterday", "yesterday"),
    ("Timeline", "timeline"),
    ("Search", "search"),
    ("Applications", "apps"),
    ("Browser History", "browser"),
    ("Files", "files"),
    ("Settings", "settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, tracker=None):
        super().__init__()
        self.tracker = tracker
        self.repo = get_repository()
        self.search_engine = get_search_engine()
        self.current_section = "today"
        # Optional hook set by the host shell: send an activity item to the hub.
        # Signature: send_to_jarvis(result: dict) -> None. Stays None standalone.
        self.send_to_jarvis = None

        self.setWindowTitle("Windows Activity Recall")
        self.resize(980, 680)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main_area(), 1)

        self._build_statusbar()

        # Debounce timer for search.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._run_search)

        # Periodic refresh of the live "Today" view + status.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._periodic_refresh)
        self._refresh_timer.start()

        self.sidebar.setCurrentRow(0)
        self._show_section("today")
        self._maybe_build_semantic()

    def _maybe_build_semantic(self) -> None:
        """If semantic indexing is enabled, (re)build the index off-thread."""
        if not get_config().semantic_indexing_enabled:
            return
        worker = SemanticBuildWorker()
        self._pool.start(worker)

    # --------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Sidebar")
        panel.setFixedWidth(210)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        brand = QLabel("⏱  Activity Recall")
        brand.setObjectName("Brand")
        v.addWidget(brand)
        sub = QLabel("Your local activity history")
        sub.setObjectName("BrandSub")
        v.addWidget(sub)

        self.sidebar = QListWidget()
        for label, _id in SECTIONS:
            QListWidgetItem(label, self.sidebar)
        self.sidebar.currentRowChanged.connect(self._on_section_changed)
        v.addWidget(self.sidebar, 1)
        return panel

    def _build_main_area(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 14, 12, 8)
        v.setSpacing(10)

        # Header + search box
        self.header = QLabel("Today")
        self.header.setObjectName("Header")
        v.addWidget(self.header)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "🔍  Search your activity history…  (try: android audio yesterday)")
        self.search_box.textChanged.connect(self._on_search_text)
        self.search_box.returnPressed.connect(self._run_search)
        search_row.addWidget(self.search_box, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Keyword", "Semantic"])
        self.mode_combo.setToolTip(
            "Keyword: fast full-text search.\n"
            "Semantic: meaning-based recall (needs semantic indexing).")
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._run_search())
        search_row.addWidget(self.mode_combo)
        self._search_row = search_row
        v.addLayout(search_row)

        self._pool = QThreadPool.globalInstance()

        self.stack = QStackedWidget()
        # Page 0: results list (shared by most sections)
        self.results = QListWidget()
        self.results.setObjectName("Results")
        self.results.setUniformItemSizes(False)
        self.results.itemActivated.connect(self._open_selected)
        self.results.itemDoubleClicked.connect(self._open_selected)
        self.results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self._context_menu)
        self.stack.addWidget(self.results)

        # Page 1: settings
        self.settings_page = SettingsPage()
        self.settings_page.changed.connect(self._on_settings_changed)
        self.settings_page.clear_requested.connect(self._clear_history)
        self.stack.addWidget(self.settings_page)

        v.addWidget(self.stack, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("Sub")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.empty_label)
        return panel

    def _build_statusbar(self) -> None:
        bar = self.statusBar()
        self.status_lbl = QLabel("")
        bar.addWidget(self.status_lbl, 1)
        self.pause_btn = QPushButton("Pause tracking")
        self.pause_btn.clicked.connect(self._toggle_pause)
        bar.addPermanentWidget(self.pause_btn)
        self._update_status()

    # -------------------------------------------------------------- sections
    def _on_section_changed(self, row: int) -> None:
        if 0 <= row < len(SECTIONS):
            self._show_section(SECTIONS[row][1])

    def _show_section(self, section: str) -> None:
        self.current_section = section
        label = next(l for l, i in SECTIONS if i == section)
        self.header.setText(label)
        if section == "settings":
            self.stack.setCurrentWidget(self.settings_page)
            self.empty_label.clear()
            return
        self.stack.setCurrentWidget(self.results)
        show_search = section == "search"
        self.search_box.setVisible(show_search)
        self.mode_combo.setVisible(show_search)
        if section == "search":
            self.search_box.setFocus()
            if not self.search_box.text().strip():
                self._populate([])
                self.empty_label.setText("Type to search your history…")
                return
            self._run_search()
        else:
            self._load_section(section)

    def _load_section(self, section: str) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results: list[dict] = []
        if section == "today":
            start = _local_midnight_utc(0)
            results = self.repo.recent_sessions(since=start, limit=300)
            results += self.repo.recent_browser_visits(limit=100)
            results += self.repo.recent_files(limit=100)
            results = [r for r in results
                       if (r.get("start_time") or now) >= start]
        elif section == "yesterday":
            start = _local_midnight_utc(1)
            end = _local_midnight_utc(0)
            results = self.repo.recent_sessions(since=start, until=end, limit=300)
            results += [r for r in self.repo.recent_browser_visits(limit=300)
                        if start <= (r.get("start_time") or now) < end]
            results += [r for r in self.repo.recent_files(limit=300)
                        if start <= (r.get("start_time") or now) < end]
        elif section == "timeline":
            results = self.repo.recent_sessions(limit=500)
            results += self.repo.recent_browser_visits(limit=200)
            results += self.repo.recent_files(limit=200)
        elif section == "browser":
            results = self.repo.recent_browser_visits(limit=400)
        elif section == "files":
            results = self.repo.recent_files(limit=400)
        elif section == "apps":
            self._load_apps()
            return
        results.sort(key=lambda r: r.get("start_time") or datetime.min,
                     reverse=True)
        self._populate(results)

    def _load_apps(self) -> None:
        stats = self.repo.application_stats(limit=100)
        rows = []
        for a in stats:
            rows.append({
                "kind": "session", "id": -1,
                "title": a["display_name"],
                "app": a["name"],
                "process_name": a["name"],
                "exe_path": a["exe_path"],
                "start_time": a["last_seen"],
                "duration_seconds": a["total_seconds"],
            })
        self._populate(rows, empty_msg="No applications tracked yet.")

    # ---------------------------------------------------------------- search
    def _on_search_text(self, _text: str) -> None:
        if self.current_section != "search":
            # Typing in the box jumps to Search.
            idx = [i for i, (_, sid) in enumerate(SECTIONS) if sid == "search"][0]
            self.sidebar.setCurrentRow(idx)
        self._search_timer.start()

    def _run_search(self) -> None:
        if self.current_section != "search":
            return
        query = self.search_box.text().strip()
        if not query:
            self._populate([])
            self.empty_label.setText("Type to search your history…")
            return
        mode = "semantic" if self.mode_combo.currentText() == "Semantic" \
            else "keyword"
        self._pending_query = query
        if mode == "semantic":
            self.empty_label.setText("Thinking… (first semantic search loads "
                                     "the model, ~20s)")
        worker = SearchWorker(query, mode)
        worker.signals.done.connect(self._on_search_done)
        worker.signals.failed.connect(self._on_search_failed)
        self._pool.start(worker)

    def _on_search_done(self, query: str, mode: str, results: list) -> None:
        # Ignore results from a stale query the user has already changed.
        if query != getattr(self, "_pending_query", query):
            return
        self._populate(results, empty_msg=f"No results for “{query}”.")

    def _on_search_failed(self, query: str, error: str) -> None:
        self._populate([])
        self.empty_label.setText(error)

    # -------------------------------------------------------------- populate
    def _populate(self, results: list[dict], empty_msg: str = "") -> None:
        self.results.clear()
        for r in results:
            item = QListWidgetItem(self.results)
            widget = make_result_widget(r)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.results.addItem(item)
            self.results.setItemWidget(item, widget)
        if not results:
            self.empty_label.setText(empty_msg or "Nothing here yet.")
        else:
            self.empty_label.clear()

    # ------------------------------------------------------------------ open
    def _open_selected(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.results.currentItem()
        if not item:
            return
        result = item.data(Qt.ItemDataRole.UserRole)
        try:
            msg = open_result(result)
            self.statusBar().showMessage(msg, 4000)
        except OpenError as exc:
            self.statusBar().showMessage(f"Could not open: {exc}", 5000)

    def _context_menu(self, pos) -> None:
        item = self.results.itemAt(pos)
        if not item:
            return
        result = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_open = menu.addAction("Open")
        act_ask = menu.addAction("Ask JARVIS about this") if self.send_to_jarvis else None
        act_del = menu.addAction("Delete from history")
        chosen = menu.exec(self.results.mapToGlobal(pos))
        if chosen == act_open:
            self._open_selected(item)
        elif act_ask is not None and chosen == act_ask:
            try:
                self.send_to_jarvis(result)
            except Exception:
                pass
        elif chosen == act_del:
            if result.get("id", -1) >= 0:
                self.repo.delete_records(result["kind"], [result["id"]])
                self.results.takeItem(self.results.row(item))

    # ---------------------------------------------------------------- status
    def _toggle_pause(self) -> None:
        if not self.tracker:
            return
        if self.tracker.is_paused:
            self.tracker.resume()
        else:
            self.tracker.pause()
        self._update_status()

    def _update_status(self) -> None:
        cfg = get_config()
        counts = self.repo.counts()
        paused = self.tracker.is_paused if self.tracker else False
        if cfg.private_mode:
            state = "🔒 Private mode — not recording"
        elif paused or not cfg.tracking_enabled:
            state = "⏸ Tracking paused"
        else:
            state = "● Tracking active"
        self.status_lbl.setText(
            f"{state}   ·   {counts['sessions']} sessions · "
            f"{counts['browser_visits']} pages · {counts['file_events']} files")
        self.pause_btn.setText(
            "Resume tracking" if paused else "Pause tracking")

    def _periodic_refresh(self) -> None:
        self._update_status()
        if self.current_section in ("today", "timeline"):
            self._load_section(self.current_section)

    # -------------------------------------------------------------- settings
    def _on_settings_changed(self) -> None:
        self._update_status()
        self._maybe_build_semantic()

    def _clear_history(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear all history",
            "Permanently delete ALL recorded activity? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            self.repo.clear_all()
            self._update_status()
            self.statusBar().showMessage("History cleared.", 4000)

    # Intercept close -> hide to tray instead of quitting (set by app.py).
    close_to_tray: bool = True
    request_quit = Signal()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.close_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()


def _local_midnight_utc(days_ago: int) -> datetime:
    """UTC-naive datetime for local midnight `days_ago` days back."""
    local_now = datetime.now().astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=days_ago)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)
