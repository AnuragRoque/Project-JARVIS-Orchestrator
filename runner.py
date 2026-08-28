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
from jarvis.app.safety import guard, install_excepthook, set_error_notifier

_SINGLETON_KEY = "jarvis-singleton-v1"
_WATCHDOG_MS = 30000  # how often to check background services are alive
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
        self.reminders_module = None
        self.reminder_popup = None
        self._modules = []
        self._server: QLocalServer | None = None

    # --------------------------------------------------------- entry point
    def run(self) -> int:
        setup_logging()
        install_excepthook()      # a bug in one feature must not kill the app
        log.info("Starting JARVIS")

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("JARVIS")
        self.app.setQuitOnLastWindowClosed(False)

        if self._already_running():
            log.info("Another instance is running — signalled it to show. Exiting.")
            return 0
        self._become_primary()

        self.settings = get_settings()
        try:
            get_database()  # create jarvis.db (WAL) on first boot
        except Exception:
            log.exception("Kernel DB init failed (continuing)")

        # Each subsystem boots independently; a failure disables that feature only.
        try:
            self._start_services()
        except Exception:
            log.exception("Service boot failed (continuing)")
        try:
            self._build_ui()
        except Exception:
            log.exception("UI boot failed")
            # Without a floating window there's nothing to show; surface via tray if any.

        self._start_watchdog()

        try:
            if self.floating and not self.settings.get("start_minimized"):
                self.floating.show_and_raise()
            if self.tray:
                self.tray.message("JARVIS", "Running in the tray. Click to open.")
        except Exception:
            log.exception("Initial surface failed (continuing)")

        code = self.app.exec()
        self._shutdown()
        return code

    # ------------------------------------------------------------ watchdog
    def _start_watchdog(self) -> None:
        """Periodically ensure the background services are still alive; restart
        any that died. Never restarts by closing anything — only revives."""
        self._watchdog = QTimer()
        self._watchdog.setInterval(_WATCHDOG_MS)
        self._watchdog.timeout.connect(guard(self._check_services, where="watchdog"))
        self._watchdog.start()

    def _check_services(self) -> None:
        for name, svc in (("activity tracker", self.tracker),
                          ("file recall", self.file_service),
                          ("browser API", self.api_server)):
            if svc is None:
                continue
            thread = getattr(svc, "_thread", None)
            if thread is not None and not thread.is_alive():
                log.warning("Service '%s' stopped — restarting", name)
                try:
                    svc.start()  # start() is idempotent / creates a fresh thread
                except Exception:
                    log.exception("Restart of '%s' failed (feature stays down)", name)

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
        try:
            self.pw_engine = PowerShellEngine()
        except Exception:
            log.exception("PowerShell engine failed to start (terminal disabled)")
            self.pw_engine = None
        self._setup_orchestrator()

        # Reminder toasts (subscribes to the reminder.due bus event).
        try:
            from jarvis.ui.reminder_popup import ReminderPopupManager
            self.reminder_popup = ReminderPopupManager(snooze_cb=self._snooze_reminder)
        except Exception:
            log.exception("Reminder popups failed to init (continuing)")

        self.floating = FloatingWindow(self.controller)
        self.floating.request_maximise.connect(self._open_main)

        self.tray = Tray(
            on_open=self._open_main,
            on_quit=self._quit,
            on_toggle_pause=self._toggle_pause if self.tracker else None,
        )
        # Surface swallowed background errors as a quiet tray nudge (throttled).
        set_error_notifier(lambda msg: self.tray and self.tray.message("JARVIS", msg))

    def _snooze_reminder(self, text: str) -> None:
        if self.reminders_module is not None:
            try:
                self.reminders_module.set_reminder(text, "in 5 minutes")
            except Exception:
                log.exception("snooze reminder failed")

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
        from jarvis.modules.reminders.module import RemindersModule
        from jarvis.modules.power.module import PowerModule
        from jarvis.modules.browser.module import BrowserModule
        from jarvis.modules.documents.module import DocumentsModule
        from jarvis.modules.typing.module import TypingModule
        from jarvis.modules.media.module import MediaModule
        from jarvis.modules.pyscript.module import PyScriptModule
        from jarvis.modules.learning.module import LearningModule
        from jarvis.modules.terminal.providers.openai_provider import OpenAIProvider
        from jarvis.modules.timeline.module import TimelineModule
        from jarvis.ui.confirm_broker import ConfirmBroker

        router = ToolRouter()
        db = get_database()

        def ctx_for(mod_id: str) -> AppContext:
            return AppContext(bus=bus, db=db, paths=paths_mod,
                              settings=ModuleSettings(mod_id), log=get_logger(mod_id),
                              speak=self.controller.speak)

        def safe_start(module, mod_id: str, setup=None):
            """Start a module defensively — a broken one is skipped, not fatal."""
            try:
                if setup is not None:
                    setup(module)
                module.start(ctx_for(mod_id))
                router.register(module.tools())
                self._modules.append(module)
                return module
            except Exception:
                log.exception("Module '%s' failed to start; skipping", mod_id)
                return None

        self._modules = []
        safe_start(TerminalModule(), "terminal",
                   setup=lambda m: m.attach_engine(self.pw_engine))
        safe_start(TimelineModule(), "timeline")
        self.reminders_module = safe_start(RemindersModule(), "reminders")
        safe_start(PowerModule(), "power")
        safe_start(BrowserModule(), "browser")
        safe_start(DocumentsModule(), "documents")
        safe_start(TypingModule(), "typing")
        safe_start(MediaModule(), "media")
        safe_start(PyScriptModule(), "pyscript")
        learning = safe_start(LearningModule(), "learning")
        if learning is not None and getattr(learning, "learner", None) is not None:
            self.controller.set_learner(learning.learner)  # remember-what-worked loop
        self.tool_router = router

        # The brain + permission gate. If any of this fails, the app still runs —
        # the controller simply falls back to plain chat.
        try:
            cfg = self.controller.cfg
            model = cfg.get("openai_model")
            provider = OpenAIProvider(api_key=cfg.openai_key, model=model)
            try:
                mode = ExecutionMode(
                    str(get_settings().get("permission_mode", "partial")).lower())
            except ValueError:
                mode = ExecutionMode.PARTIAL
            self.broker = ConfirmBroker(self.controller)
            self.coordinator = PermissionCoordinator(mode=mode, confirm=self.broker.confirm)
            self.controller.configure_orchestrator(provider, model, router,
                                                   self.coordinator)
        except Exception:
            log.exception("Orchestrator setup failed; running in plain-chat mode")

    def _ensure_main(self):
        if self.main_window is None:
            from jarvis.ui.main_window import MainWindow
            self.main_window = MainWindow(
                self.controller, tracker=self.tracker, engine=self.pw_engine,
                modules=self._modules)
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
