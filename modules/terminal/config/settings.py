from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

from jarvis.modules.terminal.core.models import ExecutionMode, ProviderType

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables from .env if present
load_dotenv(dotenv_path=ENV_PATH)


@dataclass
class Settings:
    # OpenAI Settings
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Ollama Settings
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434"))

    # Agent & Safety Settings
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "8"))
    command_timeout: int = int(os.getenv("COMMAND_TIMEOUT", "45"))
    default_execution_mode: ExecutionMode = ExecutionMode(os.getenv("DEFAULT_EXECUTION_MODE", "partial").lower())
    memory_enabled: bool = os.getenv("MEMORY_ENABLED", "true").lower() in ("true", "1", "yes")

    # Provider
    default_provider: ProviderType = ProviderType.OLLAMA

    # Database
    db_path: Path = BASE_DIR / "commands_memory.db"

    def reload() -> None:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        self.max_agent_steps = int(os.getenv("MAX_AGENT_STEPS", "8"))
        self.command_timeout = int(os.getenv("COMMAND_TIMEOUT", "45"))
        self.default_execution_mode = ExecutionMode(os.getenv("DEFAULT_EXECUTION_MODE", "partial").lower())
        self.memory_enabled = os.getenv("MEMORY_ENABLED", "true").lower() in ("true", "1", "yes")


settings = Settings()
