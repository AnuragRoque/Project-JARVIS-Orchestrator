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


class SpeechQueue:
    """A persistent background speaker. Push text; it speaks in FIFO order."""

    def __init__(self) -> None:
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._voice = ""
        self._rate = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def configure(self, voice_name: str, rate: int) -> None:
        self._voice, self._rate = voice_name, rate

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self._q.put(text)

    def clear(self) -> None:
        """Drop anything still queued (e.g. user starts a new request)."""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def _run(self) -> None:
        pythoncom.CoInitialize()
        engine = None
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                # Rebuild each turn so voice/rate changes take effect.
                engine = _make_engine(self._voice, self._rate)
                engine.Speak(text)
            except Exception:
                pass
