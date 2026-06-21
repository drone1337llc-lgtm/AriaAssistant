"""Pydantic models used for structured task outputs and Flow state."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionClass(str, Enum):
    """Classification of remediation action — drives tool choice in Fixer."""
    RESTART = "restart"             # restart a local service
    KILL_PROCESS = "kill_process"   # kill a stuck PID
    FREE_PORT = "free_port"         # kill whatever is holding a port
    SWITCH_MODEL = "switch_model"   # swap LM Studio model
    RECONFIGURE = "reconfigure"     # edit a config file (gated by safe_mode)
    ESCALATE = "escalate"           # write a report for the human, do nothing


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ServiceState(str, Enum):
    HEALTHY = "healthy"
    FAILING = "failing"
    UNKNOWN = "unknown"


class FailingService(BaseModel):
    name: str
    error: str
    last_check_iso: str


class WatchReport(BaseModel):
    """Output of the watcher task — a structured picture of service state this tick."""
    tick_number: int
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    services_checked: int = 0
    healthy: list[str] = Field(default_factory=list)
    failing: list[FailingService] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    new_log_lines: list[str] = Field(default_factory=list)
    escalation_needed: bool = False


class Diagnosis(BaseModel):
    """Output of the diagnostician task — one per failing service."""
    service: str
    symptom: str
    suspected_cause: str
    confidence: Confidence
    action_class: ActionClass
    rationale: str


class ActionRecord(BaseModel):
    """Output of the fixer task — one per diagnosis."""
    service: str
    action_class: ActionClass
    command: str
    success: bool
    output: str = ""
    error_if_failed: str = ""
    escalated_to_human: bool = False


class VerificationStatus(str, Enum):
    FIXED = "fixed"
    STILL_FAILING = "still_failing"
    REGRESSED = "regressed"


class VerificationResult(BaseModel):
    service: str
    status: VerificationStatus
    evidence: str


class LearningSummary(BaseModel):
    kb_entries_added: int = 0
    kb_entries_skipped: int = 0
    kb_path: str


# --- Wrapper models for tasks that return lists ------------------------------

class DiagnosesReport(BaseModel):
    """Wraps a list of Diagnosis for tasks.yaml `output_pydantic`."""
    items: list[Diagnosis] = Field(default_factory=list)


class ActionsReport(BaseModel):
    """Wraps a list of ActionRecord."""
    items: list[ActionRecord] = Field(default_factory=list)


class VerificationsReport(BaseModel):
    """Wraps a list of VerificationResult."""
    items: list[VerificationResult] = Field(default_factory=list)


class AriaMaintenanceState(BaseModel):
    """Structured Flow state — persisted between ticks."""
    tick_number: int = 0
    last_watch: Optional[WatchReport] = None
    last_diagnoses: list[Diagnosis] = Field(default_factory=list)
    last_actions: list[ActionRecord] = Field(default_factory=list)
    last_verifications: list[VerificationResult] = Field(default_factory=list)
    last_learning: Optional[LearningSummary] = None
    escalation_pending: list[str] = Field(default_factory=list)
    started_at_iso: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")