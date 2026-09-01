"""Configuration + persistence for Jarvis.

API keys live in `.env`. User preferences live in `settings.json`.
The Settings page can edit both; changes are written back to disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "settings.json"

# Make sure a .env exists so set_key has something to write to.
if not ENV_PATH.exists():
    sample = BASE_DIR / ".env_sample"
    ENV_PATH.write_text(sample.read_text() if sample.exists() else "", encoding="utf-8")

load_dotenv(ENV_PATH)

DEFAULT_SETTINGS = {
    "openai_model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
    "stt_language": "en-IN",          # Sarvam language_code, "unknown" = auto-detect
    "stt_model": "saarika:v2.5",      # Sarvam STT model
    "tts_voice": "",                  # empty = system default SAPI voice
    "tts_rate": 0,                    # -10..10, SAPI speaking rate
    "system_prompt": (
        "You are JARVIS, a refined, quick-witted AI assistant in the spirit of "
        "Tony Stark's assistant. Address the user politely (e.g. 'sir') on occasion "
        "but never overdo it. Be crisp, efficient and a touch dry in humour. "
        "Keep answers short and conversational since they are spoken aloud — a "
        "sentence or two unless more detail is explicitly requested. "
        "STRICT LANGUAGE RULE: The user may speak to you in Hindi, Hinglish, or any "
        "other language, but you MUST ALWAYS reply in English only. Never respond in "
        "Hindi or any non-English language, and never use Devanagari script, "
        "regardless of the language the user used."
    ),
    "always_on_top": True,
    "speak_replies": True,
    # ---- Live conversation mode ----
    "wake_word": "jarvis",       # spoken word that triggers a reply in live mode
    "require_wake_word": False,  # if True, ignore utterances without the wake word
    "silence_ms": 900,           # trailing silence that auto-ends an utterance
    "vad_threshold": 450,        # RMS level above which audio counts as speech
    # ---- Barge-in (interrupt TTS by speaking) ----
    "barge_in": True,            # let the user cut in while JARVIS is speaking
    "barge_threshold": 1100,     # higher VAD gate while speaking (curbs echo self-trigger)
    "max_spoken_chars": 360,     # cap spoken reply length (screen shows the full text)
}


class Config:
    """Live view over env keys + JSON settings with save-back helpers."""

    def __init__(self) -> None:
        self.settings = dict(DEFAULT_SETTINGS)
        if SETTINGS_PATH.exists():
            try:
                self.settings.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass

    # ---- API keys (from .env) -------------------------------------------
    @property
    def openai_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "").strip()

    @property
    def sarvam_key(self) -> str:
        return os.getenv("SARVAM_API_KEY", "").strip()

    def set_keys(self, openai_key: str, sarvam_key: str) -> None:
        os.environ["OPENAI_API_KEY"] = openai_key.strip()
        os.environ["SARVAM_API_KEY"] = sarvam_key.strip()
        set_key(str(ENV_PATH), "OPENAI_API_KEY", openai_key.strip())
        set_key(str(ENV_PATH), "SARVAM_API_KEY", sarvam_key.strip())

    # ---- Preferences (settings.json) ------------------------------------
    def get(self, key: str):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))

    def update(self, values: dict) -> None:
        self.settings.update(values)
        self.save()

    def save(self) -> None:
        SETTINGS_PATH.write_text(
            json.dumps(self.settings, indent=2), encoding="utf-8"
        )
