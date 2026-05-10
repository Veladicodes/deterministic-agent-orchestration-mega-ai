"""Deterministic failure analysis and classification."""

from __future__ import annotations

from typing import List, Dict, Any, Optional

from shared.logging import get_logger
from evaluation.schemas import FailureType, FailureRecord


class FailureAnalyzer:
    """Classifies and analyzes execution failures."""

    def __init__(self):
        """Initialize failure analyzer."""
        self._logger = get_logger("evaluation.failure_analysis")

    def classify_failure(
        self,
        job_id: str,
        agent_id: Optional[str],
        error_message: str,
        context: Dict[str, Any],
    ) -> FailureType:
        """Classify a failure deterministically.

        Args:
            job_id: Job identifier.
            agent_id: Agent where failure occurred (if known).
            error_message: Error message/description.
            context: Additional context about failure.

        Returns:
            FailureType classification.
        """
        # Retrieval failures
        if agent_id == "retriever" or "retrieval" in error_message.lower():
            if "no results" in error_message.lower() or "empty" in error_message.lower():
                return FailureType.RETRIEVAL_FAILURE
            if "timeout" in error_message.lower():
                return FailureType.TIMEOUT_FAILURE

        # Tool response issues
        if "malformed" in error_message.lower() or "invalid response" in error_message.lower():
            return FailureType.MALFORMED_TOOL_RESPONSE

        # Timeout
        if "timeout" in error_message.lower() or "exceeded" in error_message.lower():
            return FailureType.TIMEOUT_FAILURE

        # Provenance gaps
        if context.get("provenance_count", 0) == 0 or context.get("weak_sources", False):
            return FailureType.PROVENANCE_GAP

        # Synthesis failures
        if agent_id == "synthesizer" or "synthesis" in error_message.lower():
            if context.get("confidence_score", 1.0) < 0.3:
                return FailureType.LOW_CONFIDENCE_SYNTHESIS
            return FailureType.SYNTHESIS_FAILURE

        # Decomposition failures
        if agent_id == "decomposer" or "decomposition" in error_message.lower():
            return FailureType.DECOMPOSITION_FAILURE

        # Contradiction miss
        if context.get("missed_contradictions", False):
            return FailureType.CONTRADICTION_MISS

        # Ambiguity not flagged
        if context.get("ambiguous_but_not_flagged", False):
            return FailureType.AMBIGUITY_NOT_FLAGGED

        # Default to orchestration failure
        return FailureType.ORCHESTRATION_FAILURE

    def create_failure_record(
        self,
        failure_id: str,
        job_id: str,
        agent_id: Optional[str],
        error_message: str,
        context: Dict[str, Any],
    ) -> FailureRecord:
        """Create a typed failure record.

        Args:
            failure_id: Unique failure identifier.
            job_id: Job identifier.
            agent_id: Agent where failure occurred.
            error_message: Error description.
            context: Additional context.

        Returns:
            FailureRecord instance.
        """
        failure_type = self.classify_failure(job_id, agent_id, error_message, context)

        record = FailureRecord(
            failure_id=failure_id,
            job_id=job_id,
            failure_type=failure_type,
            agent_id=agent_id,
            error_message=error_message,
            recoverable=context.get("recoverable", False),
            severity=context.get("severity", "warning"),
            detected_during=context.get("phase", "unknown"),
            context=context,
        )

        return record

    def analyze_failure_patterns(
        self,
        failures: List[FailureRecord],
    ) -> Dict[str, Any]:
        """Analyze patterns across multiple failures.

        Args:
            failures: List of failure records.

        Returns:
            Pattern analysis dict.
        """
        if not failures:
            return {
                "total_failures": 0,
                "failure_types": {},
                "most_common_type": None,
                "by_agent": {},
            }

        # Count by type
        type_counts: Dict[str, int] = {}
        agent_counts: Dict[str, int] = {}
        recoverable_count = 0

        for failure in failures:
            type_name = failure.failure_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            if failure.agent_id:
                agent_counts[failure.agent_id] = agent_counts.get(failure.agent_id, 0) + 1

            if failure.recoverable:
                recoverable_count += 1

        # Find most common
        most_common = None
        max_count = 0
        for ftype, count in type_counts.items():
            if count > max_count:
                max_count = count
                most_common = ftype

        return {
            "total_failures": len(failures),
            "failure_types": type_counts,
            "most_common_type": most_common,
            "most_common_count": max_count,
            "by_agent": agent_counts,
            "recoverable_count": recoverable_count,
            "recovery_rate": recoverable_count / len(failures) if failures else 0.0,
        }

    def identify_weak_provenance(
        self,
        provenance_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Identify provenance records with weak signals.

        Args:
            provenance_records: List of provenance records.

        Returns:
            List of weak provenance records.
        """
        weak: List[Dict[str, Any]] = []

        for record in provenance_records:
            confidence = record.get("confidence", 1.0)
            hop_count = record.get("hop_number", 1)
            source_type = record.get("source_type", "unknown")

            # Weak signals: low confidence, high hop count, unreliable source
            if confidence < 0.5 or hop_count > 2 or source_type not in ["primary", "secondary"]:
                weak.append(record)

        return weak

    def check_contradiction_miss(
        self,
        expected_contradictions: int,
        detected_contradictions: int,
    ) -> bool:
        """Check if contradiction detection missed too many.

        Args:
            expected_contradictions: Expected number based on query analysis.
            detected_contradictions: Actually detected.

        Returns:
            True if too many missed.
        """
        if expected_contradictions == 0:
            return False

        miss_rate = 1.0 - (detected_contradictions / expected_contradictions)
        return miss_rate > 0.3  # If >30% missed, flag as miss
