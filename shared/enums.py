from __future__ import annotations

from enum import Enum


class FailureMode(str, Enum):
    """Canonical failure modes for tool and agent operations.

    Kept intentionally small and explicit so callers can handle specific
    failure contracts (timeout, empty, malformed) without guessing.
    """

    TIMEOUT = "timeout"
    EMPTY = "empty"
    MALFORMED = "malformed"
    INTERNAL = "internal"
    NONE = "none"


class ExecutionStatus(str, Enum):
    """High-level execution lifecycle states for tasks/agents."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskFlag(str, Enum):
    """Risk flags set during input analysis or runtime checks.

    These are intentionally coarse-grained so policies can combine them.
    """

    PII = "pii"
    VIOLENCE = "violence"
    TOXICITY = "toxicity"
    SENSITIVE = "sensitive"
    NONE = "none"


class AgentState(str, Enum):
    """Runtime states for an agent instance."""

    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


class ReviewStatus(str, Enum):
    """Review states for proposed prompt rewrites."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
