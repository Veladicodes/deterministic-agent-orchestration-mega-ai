"""ExecutionStateManager implementation.

Manages pipeline execution state transitions and persistence.
Tracks: initialized -> running -> partial_failure/failed/completed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from shared.enums import ExecutionStatus
from shared.logging import get_logger
from context.shared_context import SharedContext, ExecutionState


class ExecutionStateManager:
    """Manages pipeline execution state machine.

    Transitions:
      PENDING -> RUNNING -> (SUCCEEDED | PARTIAL_FAILURE | FAILED | CANCELLED)

    Ensures state consistency and provides explicit transition events
    for persistence and observability.
    """

    def __init__(self, job_id: str):
        """Initialize state manager for a specific job.

        Args:
            job_id: Unique identifier for this execution.
        """
        self.job_id = job_id
        self._logger = get_logger(f"state_manager.{job_id}")
        self._current_state = ExecutionStatus.PENDING
        self._state_transitions = []

    @property
    def current_state(self) -> ExecutionStatus:
        """Get current execution state."""
        return self._current_state

    @property
    def state_history(self) -> list[tuple[ExecutionStatus, datetime]]:
        """Get all state transitions with timestamps."""
        return [(state, ts) for state, ts in self._state_transitions]

    def initialize(self) -> None:
        """Initialize state to PENDING."""
        if self._current_state != ExecutionStatus.PENDING:
            return

        self._record_transition(ExecutionStatus.PENDING)

    def start_execution(self) -> None:
        """Transition to RUNNING state."""
        if self._current_state != ExecutionStatus.PENDING:
            return

        self._current_state = ExecutionStatus.RUNNING
        self._record_transition(ExecutionStatus.RUNNING)

    def mark_partial_failure(self, reason: str = "") -> None:
        """Transition to PARTIAL_FAILURE state.

        Args:
            reason: Description of what failed.
        """
        if self._current_state != ExecutionStatus.RUNNING:
            return

        self._current_state = ExecutionStatus.PARTIAL_FAILURE
        self._record_transition(ExecutionStatus.PARTIAL_FAILURE)

    def mark_failed(self, reason: str = "") -> None:
        """Transition to FAILED state.

        Args:
            reason: Description of failure.
        """
        if self._current_state not in (ExecutionStatus.RUNNING, ExecutionStatus.PARTIAL_FAILURE):
            return

        self._current_state = ExecutionStatus.FAILED
        self._record_transition(ExecutionStatus.FAILED)

    def mark_succeeded(self) -> None:
        """Transition to SUCCEEDED state."""
        if self._current_state not in (ExecutionStatus.RUNNING, ExecutionStatus.PARTIAL_FAILURE):
            return

        self._current_state = ExecutionStatus.SUCCEEDED
        self._record_transition(ExecutionStatus.SUCCEEDED)

    def mark_cancelled(self, reason: str = "") -> None:
        """Transition to CANCELLED state.

        Args:
            reason: Cancellation reason.
        """
        if self._current_state in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
            return

        self._current_state = ExecutionStatus.CANCELLED
        self._record_transition(ExecutionStatus.CANCELLED)

    def apply_to_context(self, context: SharedContext) -> None:
        """Apply current state to a SharedContext.

        Updates context's execution_state with current status and timestamps.

        Args:
            context: SharedContext to update.
        """
        context.execution_state.status = self._current_state

        if not context.execution_state.started_at and self._current_state != ExecutionStatus.PENDING:
            context.execution_state.started_at = datetime.utcnow()

        context.execution_state.updated_at = datetime.utcnow()

        self._logger.debug("applied state to context: %s", self._current_state)

    def _record_transition(self, state: ExecutionStatus) -> None:
        """Record a state transition with timestamp.

        Args:
            state: The new state.
        """
        timestamp = datetime.utcnow()
        self._state_transitions.append((state, timestamp))
        self._logger.debug("recorded transition: %s at %s", state, timestamp.isoformat())

    def is_terminal_state(self) -> bool:
        """Check if current state is terminal (no more transitions possible).

        Returns:
            True if state is SUCCEEDED, FAILED, or CANCELLED.
        """
        return self._current_state in (
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )

    def can_continue(self) -> bool:
        """Check if execution can continue (not yet in terminal state).

        Returns:
            True if not yet in terminal state.
        """
        return not self.is_terminal_state()
