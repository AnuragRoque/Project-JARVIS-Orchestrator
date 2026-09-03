"""The full tabbed control centre.

Tabs: Voice Chat · Activity Timeline · Terminal · Logs · Settings · Dashboard.
Logs / Settings are placeholders until their phases; Dashboard is 'coming soon'.
Closing the window hides it (the tray keeps the app alive) unless the Runner has
set ``close_to_tray = False`` for a real quit.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget

from jarvis.app.logsetup import get_logger
from jarvis.ui.theme import app_qss, theme_manager
from jarvis.ui.tabs.dashboard_tab import DashboardTab
from jarvis.ui.tabs.logs_tab import LogsTab
from jarvis.ui.tabs.placeholder import Placeholder
from jarvis.ui.tabs.settings_tab import SettingsTab
from jarvis.ui.tabs.terminal_tab import TerminalTab
from jarvis.ui.tabs.timeline_tab import TimelineTab
from jarvis.ui.tabs.voice_chat_tab import VoiceChatTab

log = get_logger("main_window")


class MainWindow(QMainWindow):
    close_to_tray = True

    _PREFERRED = (1180, 760)

    def __init__(self, controller, tracker=None, engine=None, modules=None,
                 on_hide=None) -> None:
        super().__init__()
        self._on_hide = on_hide
        self.setWindowTitle("JARVIS")
        self.fit_to_screen()
        self._apply_theme()
        theme_manager.changed.connect(self._apply_theme)

        tabs = QTabWidget()
        tabs.setMovable(False)
        tabs.setDocumentMode(True)
        self.tabs = tabs

        # Each tab is built defensively: if one raises, it becomes an error page
        # instead of taking down the whole window.
        self.voice_tab = self._safe_tab(
            "Voice Chat", lambda: VoiceChatTab(controller))
        self.timeline_tab = self._safe_tab(
            "Activity Timeline",
            lambda: TimelineTab(tracker=tracker, on_send_to_jarvis=self._send_to_jarvis))
        self.terminal_tab = self._safe_tab(
            "Terminal", lambda: TerminalTab(engine=engine))
        self._safe_tab("Logs", LogsTab)
        self._safe_tab("Settings", lambda: SettingsTab(controller, modules=modules))
        self._safe_tab("Dashboard", DashboardTab)

        self.setCentralWidget(tabs)

    def _apply_theme(self) -> None:
        self.setStyleSheet(app_qss(theme_manager.palette()))

    def fit_to_screen(self) -> None:
        """Size to fit the work area (never overflow) and centre it."""
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(self._PREFERRED[0], int(screen.width() * 0.95))
        h = min(self._PREFERRED[1], int(screen.height() * 0.95))
        self.resize(w, h)
        self.move(screen.center().x() - w // 2, screen.center().y() - h // 2)

    def _safe_tab(self, title: str, factory):
        try:
            widget = factory()
        except Exception:
            log.exception("Tab '%s' failed to build; showing an error page", title)
            widget = Placeholder(
                title, "This section failed to load, but the rest of JARVIS is "
                "running normally. See the logs for details.", badge="UNAVAILABLE")
        self.tabs.addTab(widget, title)
        return widget

    def _send_to_jarvis(self, result: dict) -> None:
        """Timeline → hub: switch to Voice Chat and prefill a request about the item."""
        title = (result.get("title") or result.get("path")
                 or result.get("url") or "").strip()
        if not title:
            return
        kind = result.get("kind")
        verb = "Open my file" if kind == "file" else "Reopen" if kind == "browser" else "Open"
        if not hasattr(self.voice_tab, "view"):
            return  # Voice Chat tab unavailable; nothing to prefill
        self.tabs.setCurrentWidget(self.voice_tab)
        self.voice_tab.view.prefill(f'{verb} "{title[:120]}"')

    def shutdown(self) -> None:
        try:
            self.terminal_tab.shutdown()
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.close_to_tray:
            event.ignore()
            self.hide()
            if self._on_hide:
                self._on_hide()   # bring the floating orb back (one surface at a time)
        else:
            event.accept()
