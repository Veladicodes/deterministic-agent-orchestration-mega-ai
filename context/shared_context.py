from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from shared.enums import ExecutionStatus, RiskFlag


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation.

    Lightweight, serializable record to trace calls to tools and connectors.
    """

    tool_name: str
    input: Dict[str, object] = Field(default_factory=dict)
    output: Optional[Dict[str, object]] = None
    failure: Optional[str] = None
    latency_ms: Optional[float] = None
    retries: int = 0


class ProvenanceRecord(BaseModel):
    """Provenance information used to explain sources of facts.

    Kept minimal: stable id, optional weight, and an extensible metadata map.
    """

    source_id: str
    weight: float = 1.0
    metadata: Dict[str, object] = Field(default_factory=dict)


class SubTask(BaseModel):
    """Represents a unit of work derived from the original query.

    Subtasks are intentionally simple so orchestration can compose them.
    """

    id: str
    description: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, object] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Structured results an agent may contribute to the shared context.

    Contains output text and optional structured artifacts such as tokens
    and tool-call traces. Kept minimal and extensible.
    """

    agent_id: str
    output_text: Optional[str] = None
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    metadata: Dict[str, object] = Field(default_factory=dict)


class ExecutionState(BaseModel):
    """Top-level execution state for the job.

    This is small and only tracks what the orchestrator and agents need
    without mixing in internal runtime details.
    """

    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)


class SharedContext(BaseModel):
    """Canonical shared execution context passed to agents and tools.

    - `job_id` identifies the workflow.
    - `original_query` is the user prompt / task descriptor.
    - `risk_flags` are coarse-grained signals for downstream policy checks.
    - `execution_state` is the authoritative job state object.
    - `sub_tasks`, `agent_outputs`, and `tool_call_log` capture the work
      decomposition, produced outputs, and tool-level traces respectively.
    - `token_budget_usage` is a simple map (agent_id -> tokens used).
    - `provenance_map` maps stable ids to provenance records for explainability.
    """

    job_id: str
    original_query: str
    risk_flags: List[RiskFlag] = Field(default_factory=list)
    execution_state: ExecutionState = Field(default_factory=ExecutionState)
    sub_tasks: List[SubTask] = Field(default_factory=list)
    agent_outputs: List[AgentOutput] = Field(default_factory=list)
    tool_call_log: List[ToolCallRecord] = Field(default_factory=list)
    token_budget_usage: Dict[str, int] = Field(default_factory=dict)
    provenance_map: Dict[str, ProvenanceRecord] = Field(default_factory=dict)
    final_answer: Optional[str] = None

    model_config = {
        "extra": "forbid",
    }
