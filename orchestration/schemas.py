"""Typed schemas for orchestration layer.

These models provide structured contracts for orchestration execution,
enabling deterministic behavior, serialization, and persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from shared.enums import ExecutionStatus, FailureMode


class RoutingDecision(BaseModel):
    """Deterministic routing decision recorded by the orchestrator."""

    decision_type: str
    trigger_reason: str
    confidence: float = 1.0
    selected_action: str = ""
    rejected_actions: List[str] = Field(default_factory=list)
    metadata: Dict[str, object] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RetryRecord(BaseModel):
    """Record of a single retry attempt.

    Tracks retry execution with timing and failure information.
    """

    retry_number: int = 0
    """Which retry attempt this was (0 = first attempt, 1 = first retry)."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """When this retry occurred."""

    latency_ms: float = 0.0
    """Execution time in milliseconds."""

    success: bool = False
    """Whether this attempt succeeded."""

    failure_mode: Optional[str] = None
    """Failure mode if unsuccessful (e.g., 'timeout', 'exception')."""

    error_message: Optional[str] = None
    """Human-readable error description."""

    metadata: Dict[str, object] = Field(default_factory=dict)


class FailureRecord(BaseModel):
    """Record of an orchestration failure.

    Tracks when and why orchestration failed.
    """

    agent_id: Optional[str] = None
    """Agent that failed (if agent-level failure)."""

    failure_type: str = "unknown"
    """Type: 'agent_failure', 'tool_failure', 'timeout', 'state_error', 'retry_exhausted'."""

    failure_mode: Optional[str] = None
    """Enum mode like 'TIMEOUT', 'EXCEPTION', etc."""

    error_message: str = ""
    """Detailed error description."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """When the failure occurred."""

    recoverable: bool = False
    """Whether this failure can be recovered (e.g., via retry)."""

    retries_exhausted: bool = False
    """Whether all retry attempts have been used."""

    retry_attempts: int = 0
    """Number of retry attempts made before failure."""

    metadata: Dict[str, object] = Field(default_factory=dict)


class ExecutionSummary(BaseModel):
    """Summary statistics for a complete execution.

    High-level metrics and status for a pipeline run.
    """

    job_id: str
    """Unique job identifier."""

    status: ExecutionStatus = ExecutionStatus.PENDING
    """Final execution status."""

    total_agents: int = 0
    """Total agents in the pipeline."""

    agents_succeeded: int = 0
    """Agents that completed successfully."""

    agents_failed: int = 0
    """Agents that failed."""

    agents_skipped: int = 0
    """Agents that were skipped (e.g., due to prior failure)."""

    total_retries: int = 0
    """Total retry attempts across all agents."""

    total_tool_calls: int = 0
    """Total tool invocations across all agents."""

    total_tokens_used: int = 0
    """Total tokens consumed."""

    pipeline_duration_ms: float = 0.0
    """Total pipeline execution time in milliseconds."""

    started_at: Optional[datetime] = None
    """Pipeline start timestamp."""

    completed_at: Optional[datetime] = None
    """Pipeline completion timestamp."""

    failures: List[FailureRecord] = Field(default_factory=list)
    """All failures encountered (if any)."""

    partial_failure: bool = False
    """Whether execution partially succeeded with some agents failing."""

    final_answer: Optional[str] = None
    """Final synthesized answer (if execution succeeded or partially succeeded)."""

    metadata: Dict[str, object] = Field(default_factory=dict)
    """Extensible metadata."""


class PipelineResult(BaseModel):
    """Final result from a complete pipeline execution.

    Combines execution summary, final outputs, and provenance.
    """

    success: bool = False
    """Whether the pipeline completed successfully."""

    summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    """Execution summary with metrics."""

    final_answer: Optional[str] = None
    """The final synthesized answer."""

    execution_trace: Dict[str, object] = Field(default_factory=dict)
    """Structured execution trace for debugging."""

    provenance_links: Dict[str, object] = Field(default_factory=dict)
    """Provenance map from synthesis layer."""

    agent_outputs: Dict[str, object] = Field(default_factory=dict)
    """Outputs from each agent (agent_id -> output)."""

    errors: List[str] = Field(default_factory=list)
    """All errors encountered during execution."""

    warnings: List[str] = Field(default_factory=list)
    """Non-fatal warnings during execution."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """Result timestamp."""

    model_config = {
        "extra": "forbid",
    }


class AgentExecutionEvent(BaseModel):
    """Event record for a single agent execution.

    Lightweight event for structured logging.
    """

    agent_id: str
    """Agent being executed."""

    status: ExecutionStatus = ExecutionStatus.PENDING
    """Status of execution."""

    latency_ms: float = 0.0
    """Execution time in milliseconds."""

    retries: int = 0
    """Number of retries used."""

    token_count: int = 0
    """Tokens consumed."""

    tool_calls: int = 0
    """Number of tool calls made."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """Event timestamp."""

    error: Optional[str] = None
    """Error message if failed."""

    metadata: Dict[str, object] = Field(default_factory=dict)
