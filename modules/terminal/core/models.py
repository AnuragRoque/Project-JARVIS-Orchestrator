from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExecutionMode(str, Enum):
    MANUAL = "manual"
    PARTIAL = "partial"
    AUTO = "auto"


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    READ_ONLY = "READ_ONLY"
    SAFE_ACTION = "SAFE_ACTION"
    SYSTEM_MODIFICATION = "SYSTEM_MODIFICATION"
    DATA_MODIFICATION = "DATA_MODIFICATION"
    PROCESS_CONTROL = "PROCESS_CONTROL"
    NETWORK_MODIFICATION = "NETWORK_MODIFICATION"
    SECURITY_MODIFICATION = "SECURITY_MODIFICATION"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    DESTRUCTIVE = "DESTRUCTIVE"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ProviderType(str, Enum):
    OLLAMA = "ollama"
    CHATGPT = "chatgpt"


class MatchConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class CommandRequest:
    command: str
    source: str = "agent"
    risk_level: RiskLevel = RiskLevel.SAFE
    category: RiskCategory = RiskCategory.READ_ONLY
    reason: str = "Read-only command"
    requires_confirmation: bool = False


@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    timed_out: bool = False


@dataclass
class PermissionDecision:
    allowed: bool
    mode: ExecutionMode
    risk_level: RiskLevel
    category: RiskCategory
    reason: str
    command: str
    user_decision: bool | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryMatch:
    command: str
    prompt_pattern: str
    match_id: int
    confidence: MatchConfidence = MatchConfidence.HIGH
    risk_level: RiskLevel = RiskLevel.SAFE
    param_count: int = 0
