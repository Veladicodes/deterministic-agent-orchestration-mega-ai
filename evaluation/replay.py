"""Execution replay for deterministic trace reconstruction."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional

from shared.logging import get_logger
from evaluation.schemas import ReplayTrace


class ExecutionReplayer:
    """Replays execution traces for debugging and validation."""

    def __init__(self):
        """Initialize execution replayer."""
        self._logger = get_logger("evaluation.replay")
        self._traces: Dict[str, ReplayTrace] = {}

    def _serialize_datetime(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _canonical_snapshot(self, trace_data: Dict[str, Any]) -> str:
        snapshot = {
            "query": trace_data.get("query", ""),
            "agent_sequence": trace_data.get("agent_sequence", []),
            "tool_calls": trace_data.get("tool_calls", []),
            "state_transitions": [
                [state, self._serialize_datetime(timestamp)]
                for state, timestamp in trace_data.get("state_transitions", [])
            ],
            "execution_path": trace_data.get("execution_path", {}),
        }
        return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=self._serialize_datetime)

    def compute_trace_hash(self, trace_data: Dict[str, Any]) -> str:
        """Compute a deterministic hash for a trace snapshot."""
        snapshot = self._canonical_snapshot(trace_data)
        return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()

    def create_trace(
        self,
        original_job_id: str,
        query: str,
        agent_sequence: list[str],
        tool_calls: list[Dict[str, Any]],
        state_transitions: list[tuple[str, datetime]],
        execution_path: Dict[str, Any],
    ) -> ReplayTrace:
        """Create a replay trace from execution.

        Args:
            original_job_id: Original job identifier.
            query: Query text.
            agent_sequence: Sequence of agents executed.
            tool_calls: All tool calls made.
            state_transitions: State transitions with timestamps.
            execution_path: Deterministic execution path.

        Returns:
            ReplayTrace instance.
        """
        trace = ReplayTrace(
            replay_id=original_job_id,
            original_job_id=original_job_id,
            correlation_id=original_job_id,
            query=query,
            agent_sequence=agent_sequence,
            tool_calls=tool_calls,
            state_transitions=state_transitions,
            execution_path=execution_path,
            execution_hash=self.compute_trace_hash({
                "query": query,
                "agent_sequence": agent_sequence,
                "tool_calls": tool_calls,
                "state_transitions": state_transitions,
                "execution_path": execution_path,
            }),
            created_at=datetime.utcnow(),
        )

        self._traces[original_job_id] = trace
        self._logger.debug(
            "created replay trace for job %s with %d agents, %d tool calls",
            original_job_id,
            len(agent_sequence),
            len(tool_calls),
        )

        return trace

    def get_trace(self, job_id: str) -> Optional[ReplayTrace]:
        """Get stored replay trace.

        Args:
            job_id: Job identifier.

        Returns:
            ReplayTrace or None if not found.
        """
        return self._traces.get(job_id)

    def validate_trace(self, trace: ReplayTrace) -> bool:
        """Validate trace integrity.

        Args:
            trace: ReplayTrace to validate.

        Returns:
            True if trace is valid.
        """
        # Check basic structure
        if not trace.original_job_id:
            self._logger.warning("trace missing original_job_id")
            return False

        if not trace.agent_sequence:
            self._logger.warning("trace missing agent_sequence")
            return False

        if not trace.execution_path:
            self._logger.warning("trace missing execution_path")
            return False

        # Validate agent sequence
        valid_agents = {"decomposer", "retriever", "critic", "synthesizer"}
        for agent in trace.agent_sequence:
            if agent not in valid_agents:
                self._logger.warning("trace contains invalid agent: %s", agent)
                return False

        # Validate state transitions
        if not trace.state_transitions:
            self._logger.warning("trace missing state_transitions")
            return False

        expected_hash = self.compute_trace_hash({
            "query": trace.query,
            "agent_sequence": trace.agent_sequence,
            "tool_calls": trace.tool_calls,
            "state_transitions": trace.state_transitions,
            "execution_path": trace.execution_path,
        })

        if trace.execution_hash and trace.execution_hash != expected_hash:
            self._logger.warning(
                "trace hash mismatch for job %s: expected %s got %s",
                trace.original_job_id,
                expected_hash,
                trace.execution_hash,
            )
            return False

        return True

    def compare_traces(
        self,
        trace1: ReplayTrace,
        trace2: ReplayTrace,
    ) -> Dict[str, Any]:
        """Compare two execution traces for divergence.

        Args:
            trace1: First trace.
            trace2: Second trace.

        Returns:
            Comparison dict with divergences noted.
        """
        divergences: list[str] = []

        # Compare agent sequence
        if trace1.agent_sequence != trace2.agent_sequence:
            divergences.append(
                f"agent_sequence divergence: {trace1.agent_sequence} vs {trace2.agent_sequence}"
            )

        # Compare tool call count
        if len(trace1.tool_calls) != len(trace2.tool_calls):
            divergences.append(
                f"tool_call_count divergence: {len(trace1.tool_calls)} vs {len(trace2.tool_calls)}"
            )

        # Compare state count
        if len(trace1.state_transitions) != len(trace2.state_transitions):
            divergences.append(
                f"state_transition_count divergence: {len(trace1.state_transitions)} vs {len(trace2.state_transitions)}"
            )

        if trace1.execution_hash != trace2.execution_hash:
            divergences.append(
                f"execution_hash divergence: {trace1.execution_hash} vs {trace2.execution_hash}"
            )

        return {
            "identical": len(divergences) == 0,
            "divergence_count": len(divergences),
            "divergences": divergences,
            "trace1_agents": trace1.agent_sequence,
            "trace2_agents": trace2.agent_sequence,
            "trace1_tools": len(trace1.tool_calls),
            "trace2_tools": len(trace2.tool_calls),
            "trace1_hash": trace1.execution_hash,
            "trace2_hash": trace2.execution_hash,
        }

    def replay_summary(self, trace: ReplayTrace) -> Dict[str, Any]:
        """Return a compact replay verification summary."""
        return {
            "trace_id": trace.replay_id,
            "correlation_id": trace.correlation_id or trace.original_job_id,
            "execution_hash": trace.execution_hash,
            "agent_count": len(trace.agent_sequence),
            "tool_call_count": len(trace.tool_calls),
            "state_transition_count": len(trace.state_transitions),
            "integrity_valid": self.validate_trace(trace),
        }

    def reconstruct_execution_timeline(
        self,
        trace: ReplayTrace,
    ) -> list[Dict[str, Any]]:
        """Reconstruct execution timeline from trace.

        Args:
            trace: ReplayTrace to reconstruct.

        Returns:
            Timeline of events with timestamps.
        """
        timeline: list[Dict[str, Any]] = []

        # Add agent executions
        for i, agent in enumerate(trace.agent_sequence):
            timeline.append({
                "event": "agent_start",
                "agent": agent,
                "sequence": i,
                "timestamp": None,  # Would come from actual state transitions
            })

            timeline.append({
                "event": "agent_complete",
                "agent": agent,
                "sequence": i,
                "timestamp": None,
            })

        # Add state transitions
        for state, ts in trace.state_transitions:
            timeline.append({
                "event": "state_transition",
                "state": state,
                "timestamp": ts.isoformat() if ts else None,
            })

        # Add tool calls (simplified)
        for tool_call in trace.tool_calls:
            timeline.append({
                "event": "tool_call",
                "tool": tool_call.get("tool_id", "unknown"),
                "timestamp": tool_call.get("timestamp"),
            })

        return timeline
