"""The full tabbed control centre.

Tabs: Voice Chat · Activity Timeline · Terminal · Logs · Settings · Dashboard.
Logs / Settings are placeholders until their phases; Dashboard is 'coming soon'.
Closing the window hides it (the tray keeps the app alive) unless the Runner has
set ``close_to_tray = False`` for a real quit.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from jarvis.ui.styles import APP_STYLE
from jarvis.ui.tabs.placeholder import Placeholder
from jarvis.ui.tabs.terminal_tab import TerminalTab
from jarvis.ui.tabs.timeline_tab import TimelineTab
from jarvis.ui.tabs.voice_chat_tab import VoiceChatTab


class MainWindow(QMainWindow):
    close_to_tray = True

    def __init__(self, controller, tracker=None, engine=None) -> None:
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.resize(1180, 760)
        self.setStyleSheet(APP_STYLE)

        tabs = QTabWidget()
        tabs.setMovable(False)
        tabs.setDocumentMode(True)

        self.voice_tab = VoiceChatTab(controller)
        self.timeline_tab = TimelineTab(tracker=tracker)
        self.terminal_tab = TerminalTab(engine=engine)

        logs_tab = Placeholder(
            "Detailed Logs",
            "A searchable record of every command and tool JARVIS runs — with "
            "arguments, results, and the permission decision for each. Arrives with "
            "the structured event log.",
            badge="PHASE 6",
        )
        settings_tab = Placeholder(
            "Settings",
            "Global preferences plus a section per module (voice, terminal, "
            "timeline, …), split module-wise. For now, each module keeps its own "
            "settings; the Activity Timeline tab has its own Settings section.",
            badge="PHASE 7",
        )
        dashboard_tab = Placeholder(
            "Dashboard",
            "An at-a-glance view: usage stats, active reminders, power state, and "
            "recent actions.",
            badge="COMING SOON",
        )

        tabs.addTab(self.voice_tab, "Voice Chat")
        tabs.addTab(self.timeline_tab, "Activity Timeline")
        tabs.addTab(self.terminal_tab, "Terminal")
        tabs.addTab(logs_tab, "Logs")
        tabs.addTab(settings_tab, "Settings")
        tabs.addTab(dashboard_tab, "Dashboard")

        self.tabs = tabs
        self.setCentralWidget(tabs)

    def shutdown(self) -> None:
        try:
            self.terminal_tab.shutdown()
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.close_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()
