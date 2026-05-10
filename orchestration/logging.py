"""Orchestration logging utilities.

Structured JSON logging for orchestration events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from shared.exec_logger import ExecutionLogger
from shared.logging import get_logger


class OrchestrationLogger:
    """Structured logging for orchestration events.

    Emits JSON events for:
    - Pipeline initialization
    - Agent execution start/completion
    - Retries
    - Failures
    - State transitions
    - Final completion
    """

    def __init__(self):
        """Initialize orchestration logger."""
        self._exec_logger = ExecutionLogger()
        self._logger = get_logger("orchestration")

    def log_pipeline_start(self, job_id: str, original_query: str) -> None:
        """Log pipeline start event.

        Args:
            job_id: Job identifier.
            original_query: Original user query.
        """
        self._exec_logger.log_event(
            agent_id="orchestrator",
            event_type="pipeline_start",
            job_id=job_id,
            extra={
                "query": original_query[:200],  # Truncate for logging
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        self._logger.info("pipeline started: job_id=%s", job_id)

    def log_agent_started(self, job_id: str, agent_id: str, sequence_index: int) -> None:
        """Log agent execution start.

        Args:
            job_id: Job identifier.
            agent_id: Agent being executed.
            sequence_index: Position in execution sequence.
        """
        self._exec_logger.log_event(
            agent_id=agent_id,
            event_type="agent_start",
            job_id=job_id,
            extra={
                "sequence_index": sequence_index,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        self._logger.debug("agent started: %s (index=%d)", agent_id, sequence_index)

    def log_agent_completed(self, job_id: str, agent_id: str, latency_ms: float, success: bool, tokens_used: int = 0) -> None:
        """Log agent execution completion.

        Args:
            job_id: Job identifier.
            agent_id: Agent that completed.
            latency_ms: Execution time in milliseconds.
            success: Whether execution succeeded.
            tokens_used: Tokens consumed.
        """
        self._exec_logger.log_event(
            agent_id=agent_id,
            event_type="agent_complete",
            latency=latency_ms,
            token_count=tokens_used,
            job_id=job_id,
            extra={
                "success": success,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        level = "info" if success else "warning"
        getattr(self._logger, level)("agent completed: %s (%.0fms, success=%s)", agent_id, latency_ms, success)

    def log_retry_attempt(self, job_id: str, agent_id: str, attempt_number: int, reason: str) -> None:
        """Log retry attempt.

        Args:
            job_id: Job identifier.
            agent_id: Agent being retried.
            attempt_number: Which retry attempt.
            reason: Reason for retry.
        """
        self._exec_logger.log_event(
            agent_id=agent_id,
            event_type="retry_attempt",
            job_id=job_id,
            extra={
                "attempt": attempt_number,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        self._logger.warning("retry attempt: %s (attempt=%d, reason=%s)", agent_id, attempt_number, reason)

    def log_failure(self, job_id: str, failure_type: str, agent_id: Optional[str], message: str, recoverable: bool = False) -> None:
        """Log an orchestration failure.

        Args:
            job_id: Job identifier.
            failure_type: Type of failure.
            agent_id: Agent involved (if agent-specific).
            message: Failure description.
            recoverable: Whether failure is recoverable.
        """
        self._exec_logger.log_event(
            agent_id=agent_id or "orchestrator",
            event_type="failure",
            job_id=job_id,
            extra={
                "failure_type": failure_type,
                "recoverable": recoverable,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        level = "warning" if recoverable else "error"
        getattr(self._logger, level)("failure: type=%s, agent=%s, recoverable=%s", failure_type, agent_id, recoverable)

    def log_state_transition(self, job_id: str, from_state: str, to_state: str) -> None:
        """Log state transition.

        Args:
            job_id: Job identifier.
            from_state: Previous state.
            to_state: New state.
        """
        self._exec_logger.log_event(
            agent_id="orchestrator",
            event_type="state_transition",
            job_id=job_id,
            extra={
                "from": from_state,
                "to": to_state,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        self._logger.debug("state transition: %s -> %s", from_state, to_state)

    def log_pipeline_complete(
        self,
        job_id: str,
        success: bool,
        pipeline_duration_ms: float,
        agents_executed: int,
        total_retries: int,
        errors: int,
    ) -> None:
        """Log pipeline completion.

        Args:
            job_id: Job identifier.
            success: Whether fully successful.
            pipeline_duration_ms: Total execution time.
            agents_executed: Number of agents executed.
            total_retries: Total retries used.
            errors: Number of errors encountered.
        """
        self._exec_logger.log_event(
            agent_id="orchestrator",
            event_type="pipeline_complete",
            latency=pipeline_duration_ms,
            job_id=job_id,
            extra={
                "success": success,
                "agents_executed": agents_executed,
                "total_retries": total_retries,
                "errors": errors,
                "duration_ms": pipeline_duration_ms,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        level = "info" if success else "warning"
        getattr(self._logger, level)(
            "pipeline completed: success=%s, duration=%.0fms, agents=%d, retries=%d, errors=%d",
            success,
            pipeline_duration_ms,
            agents_executed,
            total_retries,
            errors,
        )
