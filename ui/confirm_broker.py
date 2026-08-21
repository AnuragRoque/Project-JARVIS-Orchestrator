"""Voice-answerable confirmation for risky actions.

When the permission coordinator needs a yes/no, it calls :meth:`ConfirmBroker.confirm`
from the orchestrator's worker thread. The broker marshals to the GUI thread,
**speaks** the request ("Sir, confirm … Should I proceed?"), shows the modal
:class:`PermissionDialog`, and **listens for a spoken yes/no**. The first of voice
or click wins. The worker thread blocks until the user answers.

Because ``QDialog.exec()`` runs a nested event loop, the queued STT results and the
voice→dialog resolution are processed while the modal is up.
"""
from __future__ import annotations

import re
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog

from jarvis.app.logsetup import get_logger
from jarvis.modules.terminal.ui.permission_dialog import PermissionDialog
from jarvis.modules.voice.core import stt
from jarvis.ui.workers import Task

log = get_logger("confirm")

_YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
        "affirmative", "allow", "proceed", "approved", "correct", "right", "aye"}
_NO = {"no", "nope", "nah", "cancel", "stop", "reject", "negative", "never",
       "skip", "deny", "don't", "dont", "not"}
_YES_PHRASES = ("go ahead", "do it", "please do", "yes please", "carry on")
_NO_PHRASES = ("do not", "don't", "no thanks", "hold on", "never mind")


def _classify_yes_no(text: str):
    low = (text or "").strip().lower()
    if not low:
        return None
    if any(p in low for p in _NO_PHRASES):
        return False
    if any(p in low for p in _YES_PHRASES):
        return True
    words = set(re.findall(r"[a-z']+", low))
    if words & _NO:
        return False
    if words & _YES:
        return True
    return None


class _VoiceYesNo(QObject):
    """Listens for a single spoken yes/no using the shared STT stack."""
    resolved = pyqtSignal(bool)

    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self.listener = None
        self._done = False

    def start(self) -> bool:
        cfg = self.c.cfg
        if not cfg.sarvam_key:
            return False
        try:
            self.listener = stt.LiveListener(
                threshold=int(cfg.get("vad_threshold")), silence_ms=700)
        except Exception:
            self.listener = None
            return False
        self.listener.utterance.connect(self._on_utterance)
        self.listener.start()
        return True

    def _on_utterance(self, wav: bytes) -> None:
        if self._done or not wav:
            return
        task = Task(stt.transcribe, wav, self.c.cfg.sarvam_key,
                    self.c.cfg.get("stt_language"), self.c.cfg.get("stt_model"))
        task.signals.result.connect(self._classify)
        task.signals.error.connect(lambda _e: None)
        self.c.pool.start(task)

    def _classify(self, text: str) -> None:
        if self._done:
            return
        verdict = _classify_yes_no(text)
        if verdict is not None:
            self._done = True
            self.resolved.emit(verdict)

    def stop(self) -> None:
        self._done = True
        if self.listener is not None:
            self.listener.stop()
            self.listener.wait(1000)
            self.listener = None


class ConfirmBroker(QObject):
    """GUI-thread confirmation broker, callable synchronously from any thread."""

    _request = pyqtSignal(str, str, object, object)

    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._result = False
        self._request.connect(self._show)  # queued from worker → runs on GUI thread

    # called from the orchestrator worker thread
    def confirm(self, summary: str, reason: str, risk_level, category) -> bool:
        with self._lock:
            self._event.clear()
            self._result = False
            self._request.emit(summary, reason, risk_level, category)
            self._event.wait()
            return self._result

    def _show(self, summary: str, reason: str, risk_level, category) -> None:
        try:
            self.controller.speak(f"Sir, confirm. {reason}. Should I proceed?")
        except Exception:
            pass

        dlg = PermissionDialog(summary, reason, risk_level, category,
                               QApplication.activeWindow())
        voice = _VoiceYesNo(self.controller)
        voice.resolved.connect(lambda ok: dlg.accept() if ok else dlg.reject())

        started = voice.start()
        if started:
            log.info("Awaiting spoken or clicked confirmation…")
        try:
            self._result = dlg.exec() == QDialog.DialogCode.Accepted
        finally:
            voice.stop()
            self._event.set()
