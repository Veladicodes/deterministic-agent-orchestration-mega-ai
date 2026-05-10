"""Schemas for evaluation infrastructure.

Typed contracts for evaluation runs, metrics, failures, and replay traces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class FailureType(str, Enum):
    """Failure classification types."""
    RETRIEVAL_FAILURE = "retrieval_failure"
    PROVENANCE_GAP = "provenance_gap"
    CONTRADICTION_MISS = "contradiction_miss"
    TIMEOUT_FAILURE = "timeout_failure"
    ORCHESTRATION_FAILURE = "orchestration_failure"
    MALFORMED_TOOL_RESPONSE = "malformed_tool_response"
    LOW_CONFIDENCE_SYNTHESIS = "low_confidence_synthesis"
    AMBIGUITY_NOT_FLAGGED = "ambiguity_not_flagged"
    DECOMPOSITION_FAILURE = "decomposition_failure"
    SYNTHESIS_FAILURE = "synthesis_failure"


class PipelineMetrics(BaseModel):
    """Pipeline-level execution metrics."""
    
    model_config = ConfigDict(extra="forbid")

    job_id: str
    """Job identifier."""

    total_latency_ms: float
    """Total pipeline latency in milliseconds."""

    decomposer_latency_ms: float = 0.0
    """Decomposer agent latency."""

    retriever_latency_ms: float = 0.0
    """Retriever agent latency."""

    critic_latency_ms: float = 0.0
    """Critic agent latency."""

    synthesizer_latency_ms: float = 0.0
    """Synthesizer agent latency."""

    retry_count: int = 0
    """Total retry attempts across all agents."""

    tool_failure_count: int = 0
    """Number of tool failures."""

    partial_failure_occurred: bool = False
    """Whether any agent failed but pipeline continued."""

    completion_rate: float = 1.0
    """Fraction of agents that completed successfully (0.0-1.0)."""

    provenance_coverage: float = 0.0
    """Estimated coverage of provenance links (0.0-1.0)."""

    orchestration_success: bool = True
    """Whether orchestration completed without critical failure."""

    decomposition_completeness: float = 0.0
    """Estimated quality of query decomposition (0.0-1.0)."""

    retrieval_relevance_estimate: float = 0.0
    """Estimated relevance of retrieved sources (0.0-1.0)."""

    contradiction_detection_rate: float = 0.0
    """Fraction of detected contradictions vs. expected (0.0-1.0)."""

    synthesis_completeness: float = 0.0
    """Completeness of synthesized answer (0.0-1.0)."""

    confidence_score: float = 0.0
    """Final confidence score from synthesis (0.0-1.0)."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """Timestamp of metric collection."""

    metadata: Dict[str, Any] = Field(default_factory=dict)
    """Additional metadata."""


class FailureRecord(BaseModel):
    """Failure classification record."""

    model_config = ConfigDict(extra="forbid")

    failure_id: str
    """Unique failure identifier."""

    job_id: str
    """Associated job ID."""

    failure_type: FailureType
    """Classification of failure."""

    agent_id: Optional[str] = None
    """Agent where failure occurred (if applicable)."""

    error_message: str = ""
    """Error message or description."""

    recoverable: bool = False
    """Whether failure was automatically recovered."""

    severity: str = "warning"
    """Severity level: debug, info, warning, error, critical."""

    detected_during: str = ""
    """Pipeline phase where detected: decompose, retrieve, critique, synthesize."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """Failure timestamp."""

    context: Dict[str, Any] = Field(default_factory=dict)
    """Additional context."""


class ReplayTrace(BaseModel):
    """Execution trace for replay functionality."""

    model_config = ConfigDict(extra="forbid")

    replay_id: str
    """Unique replay identifier."""

    original_job_id: str
    """Original job being replayed."""

    correlation_id: str = ""
    """Request correlation identifier for trace matching."""

    query: str
    """Original query."""

    agent_sequence: List[str] = Field(default_factory=list)
    """Sequence of agents executed."""

    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    """All tool calls made during execution."""

    state_transitions: List[tuple[str, datetime]] = Field(default_factory=list)
    """State machine transitions with timestamps."""

    execution_path: Dict[str, Any] = Field(default_factory=dict)
    """Deterministic execution path for reconstruction."""

    execution_hash: str = ""
    """Deterministic hash of the replay snapshot."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    """When trace was created."""

    replayed_at: Optional[datetime] = None
    """When trace was replayed (if applicable)."""

    replay_successful: bool = False
    """Whether replay succeeded."""

    replay_divergence: Optional[str] = None
    """Description of any divergence from original."""


class EvaluationRunMetadata(BaseModel):
    """Metadata for an evaluation run."""

    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str
    """Unique evaluation run identifier."""

    dataset_id: str
    """Evaluation dataset version."""

    query_count: int
    """Number of queries evaluated."""

    category_distribution: Dict[str, int] = Field(default_factory=dict)
    """Count of queries per category."""

    started_at: datetime = Field(default_factory=datetime.utcnow)
    """When evaluation started."""

    completed_at: Optional[datetime] = None
    """When evaluation completed."""

    duration_seconds: float = 0.0
    """Total evaluation duration."""

    succeeded_queries: int = 0
    """Number of queries completed successfully."""

    failed_queries: int = 0
    """Number of queries failed."""

    partial_failures: int = 0
    """Number of queries with partial failures."""

    notes: str = ""
    """Evaluation notes."""


class EvaluationSummary(BaseModel):
    """Summary statistics from an evaluation run."""

    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str
    """Evaluation run identifier."""

    dataset_id: str
    """Dataset version."""

    total_queries: int
    """Total queries evaluated."""

    completion_rate: float
    """Fraction of queries completing (0.0-1.0)."""

    avg_total_latency_ms: float
    """Average total pipeline latency."""

    p50_latency_ms: float
    """50th percentile latency."""

    p95_latency_ms: float
    """95th percentile latency."""

    p99_latency_ms: float
    """99th percentile latency."""

    max_latency_ms: float
    """Maximum latency observed."""

    avg_retry_count: float
    """Average retries per query."""

    total_failures: int
    """Total failure records."""

    failure_distribution: Dict[str, int] = Field(default_factory=dict)
    """Count of each failure type."""

    avg_provenance_coverage: float
    """Average provenance coverage across queries."""

    avg_confidence_score: float
    """Average final confidence score."""

    normal_query_success_rate: float
    """Success rate for 'normal' category queries."""

    ambiguous_query_success_rate: float
    """Success rate for 'ambiguous' category queries."""

    adversarial_query_success_rate: float
    """Success rate for 'adversarial' category queries."""

    contradiction_query_success_rate: float
    """Success rate for 'contradiction_prone' category queries."""

    provenance_query_success_rate: float
    """Success rate for 'provenance_sensitive' category queries."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """Summary creation timestamp."""
