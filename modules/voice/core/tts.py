"""Text-to-speech using the free built-in Windows SAPI voices (via pywin32).

`SpeechQueue` runs on its own thread so sentences produced by the streaming
chat reply can be spoken the instant they're ready, in order, without blocking
the UI or overlapping each other.
"""
from __future__ import annotations

import queue
import threading

import pythoncom
import win32com.client


def list_voices() -> list[str]:
    """Return the display names of installed SAPI voices."""
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        return [v.GetDescription() for v in voice.GetVoices()]
    except Exception:
        return []
    finally:
        pythoncom.CoUninitialize()


def speak(text: str, voice_name: str = "", rate: int = 0) -> None:
    """Speak `text` synchronously (blocking). For one-off use off the UI thread."""
    if not text:
        return
    pythoncom.CoInitialize()
    try:
        engine = _make_engine(voice_name, rate)
        engine.Speak(text)
    finally:
        pythoncom.CoUninitialize()


def _make_engine(voice_name: str, rate: int):
    engine = win32com.client.Dispatch("SAPI.SpVoice")
    if voice_name:
        for v in engine.GetVoices():
            if v.GetDescription() == voice_name:
                engine.Voice = v
                break
    engine.Rate = max(-10, min(10, int(rate)))
    return engine


# SAPI SpVoice.Speak flags
_SVSF_ASYNC = 1
_SVSF_PURGE = 2


class SpeechQueue:
    """A persistent background speaker. Push text; it speaks in FIFO order.

    Speaking is asynchronous and *interruptible*: :meth:`stop` purges whatever is
    playing and drops the backlog (used for barge-in — the user starts talking
    over JARVIS). ``on_finished`` fires once the queue drains after speaking, so
    the caller can resume listening.
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._voice = ""
        self._rate = 0
        self._interrupt = threading.Event()
        self._speaking = False
        self.on_finished = None  # called from the TTS thread when the queue empties
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def configure(self, voice_name: str, rate: int) -> None:
        self._voice, self._rate = voice_name, rate

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self._interrupt.clear()
            self._q.put(text)

    @property
    def is_speaking(self) -> bool:
        return self._speaking or not self._q.empty()

    def clear(self) -> None:
        """Drop anything still queued (e.g. user starts a new request)."""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def stop(self) -> None:
        """Interrupt current speech and drop the backlog (barge-in)."""
        self._interrupt.set()
        self.clear()

    def _run(self) -> None:
        pythoncom.CoInitialize()
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                # Rebuild each turn so voice/rate changes take effect.
                engine = _make_engine(self._voice, self._rate)
                self._speaking = True
                engine.Speak(text, _SVSF_ASYNC)
                while not engine.WaitUntilDone(40):
                    if self._interrupt.is_set():
                        engine.Speak("", _SVSF_PURGE)  # purge on our own thread
                        break
            except Exception:
                pass
            finally:
                self._speaking = False
            # Fire idle callback only when nothing is queued and not interrupted.
            if self._q.empty() and not self._interrupt.is_set() and self.on_finished:
                try:
                    self.on_finished()
                except Exception:
                    pass
