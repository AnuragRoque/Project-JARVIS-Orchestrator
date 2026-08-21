"""The shared voice/chat brain.

One :class:`VoiceController` owns the single microphone pipeline (STT), the
speech queue (TTS), the OpenAI chat call, and the conversation history. Both the
floating orb and the Voice Chat tab subscribe to its signals and render the same
conversation — so there is never a second mic contending for the device.

In Phase 2 the ``_ask`` chat call is swapped for the tool-calling orchestrator;
the signal surface stays the same, so the views don't change.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from jarvis.app.data.db import get_database
from jarvis.app.logsetup import get_logger
from jarvis.app.orchestrator import Orchestrator
from jarvis.app.prompts import SYSTEM_PROMPT as DEFAULT_SYSTEM_PROMPT
from jarvis.modules.voice.config import Config
from jarvis.modules.voice.core import chat, stt, tts
from jarvis.ui.workers import StreamTask, Task

log = get_logger("voice")

MAX_HISTORY = 12
_SENTENCE_END = ".!?\n"


class VoiceController(QObject):
    # ---- outward signals (UI views subscribe) ----
    status_changed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    listening_changed = pyqtSignal(bool)   # hands-free live mode on/off
    recording_changed = pyqtSignal(bool)   # one-shot mic on/off
    user_said = pyqtSignal(str)            # a user message entered the conversation
    reply_started = pyqtSignal()           # a new assistant reply begins
    reply_chunk = pyqtSignal(str)          # streamed delta of the current reply
    reply_finished = pyqtSignal(str)       # final assistant text
    error_occurred = pyqtSignal(str)
    tool_started = pyqtSignal(str, str)    # tool name, args summary
    tool_finished = pyqtSignal(str, str)   # tool name, result preview
    permission_mode_changed = pyqtSignal(str)  # auto | partial | manual

    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config()
        self.pool = QThreadPool.globalInstance()
        self.recorder = stt.Recorder()
        self.listener: stt.LiveListener | None = None
        self.speech = tts.SpeechQueue()
        self.speech.configure(self.cfg.get("tts_voice"), self.cfg.get("tts_rate"))
        self.history: list[dict] = []

        self._live = False
        self._busy = False
        self._speak = False
        self._stream_text = ""
        self._spoken_upto = 0

        # Orchestrator wiring. When configured, chat routes through the
        # tool-calling orchestrator; otherwise it falls back to plain streaming.
        self._use_orchestrator = False
        self._provider = None
        self._model = ""
        self._router = None
        self._coordinator = None
        self._gate = None
        self._system_prompt = DEFAULT_SYSTEM_PROMPT
        self._orch: Orchestrator | None = None

    def configure_orchestrator(self, provider, model: str, router,
                               coordinator=None, system_prompt: str | None = None) -> None:
        """Enable tool-calling: route chat through the orchestrator."""
        self._provider = provider
        self._model = model
        self._router = router
        self._coordinator = coordinator
        self._gate = coordinator.gate if coordinator is not None else None
        if system_prompt:
            self._system_prompt = system_prompt
        self._use_orchestrator = provider is not None and router is not None
        log.info("Orchestrator %s (model=%s, tools=%d, mode=%s)",
                 "enabled" if self._use_orchestrator else "disabled",
                 model, len(router.names()) if router else 0,
                 self.permission_mode)

    # ---- permission mode (Auto / Partial / Manual) ----
    @property
    def permission_mode(self) -> str:
        if self._coordinator is not None:
            return self._coordinator.mode.value
        return "partial"

    def set_permission_mode(self, mode: str) -> None:
        mode = (mode or "").lower()
        if self._coordinator is not None:
            self._coordinator.set_mode(mode)
        try:
            from jarvis.app.config.settings import get_settings
            get_settings().set("permission_mode", mode)
        except Exception:
            log.debug("persist permission_mode failed", exc_info=True)
        self.permission_mode_changed.emit(mode)

    # ------------------------------------------------------------- helpers
    def _set_status(self, text: str) -> None:
        self.status_changed.emit(text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    def speak(self, text: str) -> None:
        """Speak arbitrary text (also used by other modules, e.g. reminders)."""
        self.speech.configure(self.cfg.get("tts_voice"), self.cfg.get("tts_rate"))
        self.speech.say(text)

    @property
    def is_live(self) -> bool:
        return self._live

    @property
    def is_busy(self) -> bool:
        return self._busy

    # --------------------------------------------------------------- chat
    def send_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self._busy:
            return
        self.user_said.emit(text)
        self._set_busy(True)
        self._ask(text)

    def _ask(self, prompt: str) -> None:
        if self._use_orchestrator:
            self._ask_orchestrator(prompt)
        else:
            self._ask_stream(prompt)

    def _prepare_reply(self) -> None:
        self._set_status("Thinking…")
        self.speech.clear()
        self.speech.configure(self.cfg.get("tts_voice"), self.cfg.get("tts_rate"))
        self._speak = bool(self.cfg.get("speak_replies"))
        self._stream_text = ""
        self._spoken_upto = 0

    def _ask_stream(self, prompt: str) -> None:
        self._prepare_reply()
        self.reply_started.emit()
        task = StreamTask(
            chat.stream, prompt, self.cfg.openai_key,
            self.cfg.get("openai_model"), self.cfg.get("system_prompt"),
            list(self.history),
        )
        task.signals.chunk.connect(self._on_chunk)
        task.signals.result.connect(lambda r: self._on_reply(prompt, r))
        task.signals.error.connect(self._on_error)
        self.pool.start(task)

    def _ask_orchestrator(self, prompt: str) -> None:
        self._prepare_reply()
        self._orch = Orchestrator(
            self._provider, self._model, self._build_messages(prompt),
            self._router, self._gate,
        )
        self._orch.status.connect(self._set_status)
        self._orch.tool_started.connect(self.tool_started.emit)
        self._orch.tool_finished.connect(self.tool_finished.emit)
        self._orch.final.connect(lambda t: self._on_orch_final(prompt, t))
        self._orch.failed.connect(self._on_error)
        self._orch.start()

    def _build_messages(self, prompt: str) -> list[dict]:
        msgs = [{"role": "system", "content": self._system_prompt}]
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _on_orch_final(self, prompt: str, reply: str) -> None:
        self.reply_started.emit()
        self.reply_finished.emit(reply or "…")
        self._finalize_reply(prompt, reply)

    def _on_chunk(self, delta: str) -> None:
        self._stream_text += delta
        self.reply_chunk.emit(delta)
        if self._speak and not self._live:
            self._flush_spoken_sentences(final=False)

    def _flush_spoken_sentences(self, final: bool) -> None:
        text = self._stream_text
        cut = self._spoken_upto
        if final:
            chunk = text[cut:].strip()
            if chunk:
                self.speech.say(chunk)
            self._spoken_upto = len(text)
            return
        last = max((text.rfind(ch) for ch in _SENTENCE_END), default=-1)
        if last >= cut:
            chunk = text[cut:last + 1].strip()
            if chunk:
                self.speech.say(chunk)
            self._spoken_upto = last + 1

    def _on_reply(self, prompt: str, reply: str) -> None:
        self.reply_finished.emit(reply or "…")
        self._finalize_reply(prompt, reply)

    def _finalize_reply(self, prompt: str, reply: str) -> None:
        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": reply})
        self.history[:] = self.history[-MAX_HISTORY:]
        self._persist(prompt, reply)

        if self._live:
            if self._speak and reply:
                task = Task(tts.speak, reply, self.cfg.get("tts_voice"),
                            self.cfg.get("tts_rate"))
                task.signals.finished.connect(self._resume_live)
                self._set_status("Speaking…")
                self.pool.start(task)
            else:
                self._resume_live()
            return

        if self._speak:
            self._stream_text = reply
            self._flush_spoken_sentences(final=True)
        self._set_busy(False)
        self._set_status("Ready")

    @staticmethod
    def _persist(prompt: str, reply: str) -> None:
        """Best-effort append of the turn to the conversations table."""
        try:
            from datetime import datetime
            db = get_database()
            with db.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS conversations ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, role TEXT, "
                    "content TEXT)"
                )
                now = datetime.now().isoformat(timespec="seconds")
                cur.execute(
                    "INSERT INTO conversations (ts, role, content) VALUES (?,?,?)",
                    (now, "user", prompt))
                cur.execute(
                    "INSERT INTO conversations (ts, role, content) VALUES (?,?,?)",
                    (now, "assistant", reply))
        except Exception:
            log.debug("conversation persist skipped", exc_info=True)

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.recording_changed.emit(False)
        self.speech.clear()
        self.error_occurred.emit(message)
        if self._live:
            self._resume_live()
        else:
            self._set_status("Error")

    # ------------------------------------------------------ one-shot mic
    def toggle_record(self) -> None:
        if self._busy or self._live:
            return
        if not self.recorder.recording:
            try:
                self.recorder.start()
            except Exception as exc:
                self._set_status(f"Mic error: {exc}")
                return
            self.recording_changed.emit(True)
            self._set_status("Listening… tap to stop")
        else:
            self.recording_changed.emit(False)
            wav = self.recorder.stop()
            if not wav:
                self._set_status("No audio captured")
                return
            self._set_busy(True)
            self._set_status("Transcribing…")
            self._transcribe(wav, self._on_transcript)

    def _transcribe(self, wav: bytes, on_result) -> None:
        task = Task(
            stt.transcribe, wav, self.cfg.sarvam_key,
            self.cfg.get("stt_language"), self.cfg.get("stt_model"),
        )
        task.signals.result.connect(on_result)
        task.signals.error.connect(self._on_error)
        self.pool.start(task)

    def _on_transcript(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            self._set_busy(False)
            self._set_status("Didn't catch that")
            return
        self.user_said.emit(text)
        self._ask(text)

    # -------------------------------------------------- live conversation
    def toggle_live(self) -> None:
        if self._live:
            self._stop_live()
        else:
            self._start_live()

    def _start_live(self) -> None:
        if self.recorder.recording:
            self.recorder.stop()
            self.recording_changed.emit(False)
        self._live = True
        self.listening_changed.emit(True)
        self.speech.configure(self.cfg.get("tts_voice"), self.cfg.get("tts_rate"))
        try:
            self.listener = stt.LiveListener(
                threshold=int(self.cfg.get("vad_threshold")),
                silence_ms=int(self.cfg.get("silence_ms")),
            )
        except Exception as exc:
            self._live = False
            self.listening_changed.emit(False)
            self._set_status(f"Mic error: {exc}")
            return
        self.listener.utterance.connect(self._on_live_utterance)
        self.listener.speech_started.connect(lambda: self._set_status("Hearing you…"))
        self.listener.start()
        self._set_status("Live — listening… tap to stop")

    def _stop_live(self) -> None:
        self._live = False
        if self.listener is not None:
            self.listener.stop()
            self.listener.wait(1500)
            self.listener = None
        self.speech.clear()
        self.listening_changed.emit(False)
        self._set_busy(False)
        self._set_status("Ready")

    def _on_live_utterance(self, wav: bytes) -> None:
        if self._busy or not self._live or not wav:
            return
        if self.listener is not None:
            self.listener.pause()
        self._set_busy(True)
        self._set_status("Transcribing…")
        self._transcribe(wav, self._on_live_transcript)

    def _on_live_transcript(self, text: str) -> None:
        text = self._apply_wake_word((text or "").strip())
        if not text:
            self._set_busy(False)
            self._resume_live()
            return
        self.user_said.emit(text)
        self._ask(text)

    def _apply_wake_word(self, text: str) -> str:
        wake = (self.cfg.get("wake_word") or "").strip().lower()
        if not text:
            return ""
        low = text.lower()
        if self.cfg.get("require_wake_word") and wake and wake not in low:
            return ""
        if wake and low.startswith(wake):
            text = text[len(wake):].lstrip(" ,.:!?-").strip() or text
        return text

    def _resume_live(self) -> None:
        if not self._live:
            self._set_status("Ready")
            return
        self._set_busy(False)
        if self.listener is not None:
            self.listener.resume()
        self._set_status("Live — listening… tap to stop")

    # ------------------------------------------------------------- teardown
    def shutdown(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener.wait(1500)
            self.listener = None
        self.speech.clear()
