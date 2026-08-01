"""Speech-to-text: microphone capture + Sarvam AI transcription."""
from __future__ import annotations

import io
import wave
from collections import deque

import numpy as np
import requests
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SAMPLE_RATE = 16000
CHANNELS = 1
PREROLL_MS = 320   # audio kept before speech onset so first phonemes aren't clipped


class Recorder:
    """Toggle recorder. `start()` opens the mic, `stop()` returns 16-bit PCM WAV bytes."""

    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self.recording = False

    def _callback(self, indata, frames, time, status):  # noqa: ANN001
        self._frames.append(indata.copy())

    def start(self) -> None:
        if self.recording:
            return
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()
        self.recording = True

    def stop(self) -> bytes:
        """Stop recording and return a WAV byte-string (empty if nothing captured)."""
        if not self.recording:
            return b""
        self.recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return b""
        audio = np.concatenate(self._frames, axis=0)
        return _to_wav_bytes(audio)


class LiveListener(QThread):
    """Continuous hands-free listener with energy-based voice activity detection.

    Emits `utterance(wav_bytes)` each time the speaker finishes talking (detected
    by a run of trailing silence). Runs until `stop()`. Use `pause()` while the
    assistant is speaking so it doesn't transcribe its own voice.
    """

    utterance = pyqtSignal(bytes)
    speech_started = pyqtSignal()

    def __init__(self, threshold: int = 450, silence_ms: int = 900,
                 min_speech_ms: int = 300) -> None:
        super().__init__()
        self.threshold = threshold
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self._running = False
        self._paused = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        block = 512                        # ~32 ms per read at 16 kHz (finer VAD)
        block_ms = block / SAMPLE_RATE * 1000
        preroll = deque(maxlen=max(1, int(PREROLL_MS / block_ms)))
        frames: list[np.ndarray] = []
        speaking = False
        silence_ms = 0.0
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                dtype="int16", blocksize=block) as stream:
                while self._running:
                    data, _ = stream.read(block)
                    if self._paused:
                        preroll.clear()
                        frames, speaking, silence_ms = [], False, 0.0
                        continue
                    rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
                    if rms >= self.threshold:
                        if not speaking:
                            speaking = True
                            frames = list(preroll)   # include audio before onset
                            preroll.clear()
                            self.speech_started.emit()
                        silence_ms = 0.0
                        frames.append(data.copy())
                    elif speaking:
                        frames.append(data.copy())   # keep trailing audio (plosives)
                        silence_ms += block_ms
                        if silence_ms >= self.silence_ms:
                            audio = np.concatenate(frames, axis=0)
                            speech_ms = len(audio) / SAMPLE_RATE * 1000 - self.silence_ms
                            frames, speaking, silence_ms = [], False, 0.0
                            if speech_ms >= self.min_speech_ms:
                                self.utterance.emit(_to_wav_bytes(audio))
                    else:
                        preroll.append(data.copy())  # rolling pre-speech buffer
        except Exception:
            pass


def _normalize(audio: np.ndarray) -> np.ndarray:
    """Lift quiet speech toward full scale for cleaner recognition.

    Only boosts when there is real signal, and caps the gain so background
    hiss in near-silent clips isn't amplified into noise.
    """
    if not audio.size:
        return audio.astype(np.int16)
    rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
    if rms < 120:           # essentially silence/noise — leave it alone
        return audio.astype(np.int16)
    peak = int(np.max(np.abs(audio)))
    target = int(0.95 * 32767)
    if peak >= target:
        return audio.astype(np.int16)
    gain = min(target / peak, 6.0)
    boosted = np.clip(audio.astype(np.float32) * gain, -32768, 32767)
    return boosted.astype(np.int16)


def _to_wav_bytes(audio: np.ndarray) -> bytes:
    audio = _normalize(audio)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def transcribe(wav_bytes: bytes, api_key: str, language: str, model: str) -> str:
    """Send WAV audio to Sarvam and return the transcript text."""
    if not wav_bytes:
        return ""
    if not api_key:
        raise RuntimeError("Missing Sarvam API key. Add it in Settings.")

    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {"model": model}
    # v2.5 supports "unknown" for auto language detection.
    if language and language.lower() != "unknown":
        data["language_code"] = language
    else:
        data["language_code"] = "unknown"

    resp = requests.post(
        SARVAM_STT_URL,
        headers={"api-subscription-key": api_key},
        files=files,
        data=data,
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Sarvam STT error {resp.status_code}: {resp.text[:200]}")
    return (resp.json().get("transcript") or "").strip()
