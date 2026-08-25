"""JARVIS runner: single-instance guard, service boot, tray, and windows.

One process owns everything: it starts the background services (activity capture,
file recall, the browser API), keeps a floating orb + tray icon, and lazily opens
the tabbed control centre. A second launch just surfaces the running instance.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from jarvis.app.config.settings import get_settings
from jarvis.app.data.db import get_database
from jarvis.app.logsetup import get_logger, setup_logging

_SINGLETON_KEY = "jarvis-singleton-v1"
log = get_logger("runner")


class Runner:
    def __init__(self) -> None:
        self.app: QApplication | None = None
        self.settings = None
        self.controller = None
        self.floating = None
        self.main_window = None
        self.tray = None
        self.tracker = None
        self.file_service = None
        self.api_server = None
        self.pw_engine = None
        self.tool_router = None
        self.coordinator = None
        self.broker = None
        self._modules = []
        self._server: QLocalServer | None = None

    # --------------------------------------------------------- entry point
    def run(self) -> int:
        setup_logging()
        log.info("Starting JARVIS")

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("JARVIS")
        self.app.setQuitOnLastWindowClosed(False)

        if self._already_running():
            log.info("Another instance is running — signalled it to show. Exiting.")
            return 0
        self._become_primary()

        self.settings = get_settings()
        get_database()  # create jarvis.db (WAL) on first boot

        self._start_services()
        self._build_ui()

        if not self.settings.get("start_minimized"):
            self.floating.show_and_raise()
        if self.tray:
            self.tray.message("JARVIS", "Running in the tray. Click to open.")

        code = self.app.exec()
        self._shutdown()
        return code

    # ---------------------------------------------------- single instance
    def _already_running(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(_SINGLETON_KEY)
        if socket.waitForConnected(200):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            return True
        return False

    def _become_primary(self) -> None:
        QLocalServer.removeServer(_SINGLETON_KEY)  # clear any stale socket
        self._server = QLocalServer()
        self._server.listen(_SINGLETON_KEY)
        self._server.newConnection.connect(self._on_second_instance)

    def _on_second_instance(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: conn.readAll())
        # Whatever the message, bring ourselves forward.
        QTimer.singleShot(0, self._surface)

    def _surface(self) -> None:
        if self.main_window and self.main_window.isVisible():
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
        elif self.floating:
            self.floating.show_and_raise()

    # ------------------------------------------------------------ services
    def _start_services(self) -> None:
        """Boot the Qt-free background services (best-effort; failures are logged)."""
        try:
            from jarvis.modules.timeline.recall.capture import TrackerService
            self.tracker = TrackerService()
            self.tracker.start()
            log.info("Activity tracker started")
        except Exception:
            log.exception("Activity tracker failed to start (continuing)")

        try:
            from jarvis.modules.timeline.recall.files import FileRecallService
            self.file_service = FileRecallService()
            self.file_service.start()
            log.info("File recall service started")
        except Exception:
            log.exception("File recall service failed to start (continuing)")

        try:
            from jarvis.modules.timeline.recall.api import ApiServer
            self.api_server = ApiServer()
            self.api_server.start()
            log.info("Browser API started")
        except Exception:
            log.exception("Browser API failed to start (continuing)")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        from jarvis.modules.terminal.tools.powershell import PowerShellEngine
        from jarvis.ui.floating_window import FloatingWindow
        from jarvis.ui.tray import Tray
        from jarvis.ui.voice_controller import VoiceController

        self.controller = VoiceController()
        # One shared PowerShell engine: the orchestrator's commands run here and
        # also surface in Tab 3's live terminal.
        self.pw_engine = PowerShellEngine()
        self._setup_orchestrator()

        self.floating = FloatingWindow(self.controller)
        self.floating.request_maximise.connect(self._open_main)

        self.tray = Tray(
            on_open=self._open_main,
            on_quit=self._quit,
            on_toggle_pause=self._toggle_pause if self.tracker else None,
        )

    def _setup_orchestrator(self) -> None:
        """Register module tools and point the controller at the orchestrator."""
        from jarvis.app.bus import bus
        from jarvis.app.config import paths as paths_mod
        from jarvis.app.config.settings import ModuleSettings, get_settings
        from jarvis.app.permissions import PermissionCoordinator
        from jarvis.app.registry import AppContext
        from jarvis.app.tool_router import ToolRouter
        from jarvis.modules.terminal.core.models import ExecutionMode
        from jarvis.modules.terminal.module import TerminalModule
        from jarvis.modules.terminal.providers.openai_provider import OpenAIProvider
        from jarvis.modules.timeline.module import TimelineModule
        from jarvis.ui.confirm_broker import ConfirmBroker

        router = ToolRouter()
        db = get_database()

        def ctx_for(mod_id: str) -> AppContext:
            return AppContext(bus=bus, db=db, paths=paths_mod,
                              settings=ModuleSettings(mod_id), log=get_logger(mod_id),
                              speak=self.controller.speak)

        term = TerminalModule()
        term.attach_engine(self.pw_engine)     # share the GUI-thread engine
        term.start(ctx_for("terminal"))
        tl = TimelineModule()
        tl.start(ctx_for("timeline"))
        self._modules = [term, tl]
        for m in self._modules:
            router.register(m.tools())
        self.tool_router = router

        cfg = self.controller.cfg
        model = cfg.get("openai_model")
        provider = OpenAIProvider(api_key=cfg.openai_key, model=model)

        # Permission mode from global settings; risky actions are confirmed via a
        # spoken + clickable prompt (voice yes/no or button).
        try:
            mode = ExecutionMode(str(get_settings().get("permission_mode", "partial")).lower())
        except ValueError:
            mode = ExecutionMode.PARTIAL
        self.broker = ConfirmBroker(self.controller)
        self.coordinator = PermissionCoordinator(mode=mode, confirm=self.broker.confirm)

        self.controller.configure_orchestrator(provider, model, router,
                                               self.coordinator)

    def _ensure_main(self):
        if self.main_window is None:
            from jarvis.ui.main_window import MainWindow
            self.main_window = MainWindow(
                self.controller, tracker=self.tracker, engine=self.pw_engine)
        return self.main_window

    def _open_main(self) -> None:
        win = self._ensure_main()
        win.show()
        win.raise_()
        win.activateWindow()

    def _toggle_pause(self) -> bool:
        if not self.tracker:
            return False
        if self.tracker.is_paused:
            self.tracker.resume()
        else:
            self.tracker.pause()
        return self.tracker.is_paused

    # ------------------------------------------------------------ teardown
    def _quit(self) -> None:
        log.info("Quit requested")
        if self.tray:
            self.tray.hide()
        if self.app:
            self.app.quit()

    def _shutdown(self) -> None:
        log.info("Shutting down services")
        if self.main_window:
            self.main_window.close_to_tray = False
            self.main_window.shutdown()
        for m in self._modules:
            try:
                m.stop()
            except Exception:
                log.exception("Module stop failed")
        if self.pw_engine:
            try:
                self.pw_engine.shutdown()
            except Exception:
                log.exception("PowerShell engine shutdown failed")
        if self.controller:
            self.controller.shutdown()
        for svc in (self.tracker, self.file_service):
            try:
                if svc:
                    svc.stop()
            except Exception:
                log.exception("Service stop failed")
        try:
            if self.api_server:
                self.api_server.stop()
        except Exception:
            log.exception("API stop failed")


def main() -> int:
    return Runner().run()


if __name__ == "__main__":
    sys.exit(main())
