"""Evaluation runner - orchestrates evaluation of the full pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from shared.logging import get_logger
from evaluation.dataset import EvaluationDataset
from evaluation.metrics import MetricsCollector
from evaluation.failure_analysis import FailureAnalyzer
from evaluation.schemas import (
    PipelineMetrics,
    FailureRecord,
    EvaluationRunMetadata,
)


class EvaluationRunner:
    """Orchestrates deterministic evaluation runs."""

    def __init__(self, dataset: EvaluationDataset):
        """Initialize evaluation runner.

        Args:
            dataset: Loaded EvaluationDataset.
        """
        self._logger = get_logger("evaluation.runner")
        self.dataset = dataset
        self.metrics_collector = MetricsCollector()
        self.failure_analyzer = FailureAnalyzer()

        self.evaluation_run_id = str(uuid.uuid4())
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        self._failures: List[FailureRecord] = []
        self._execution_results: List[Dict[str, Any]] = []

    def initialize(self) -> EvaluationRunMetadata:
        """Initialize evaluation run.

        Returns:
            EvaluationRunMetadata for tracking.
        """
        self.started_at = datetime.utcnow()
        distribution = self.dataset.category_distribution()

        metadata = EvaluationRunMetadata(
            evaluation_run_id=self.evaluation_run_id,
            dataset_id=self.dataset.dataset_id,
            query_count=self.dataset.total_entries(),
            category_distribution=distribution,
            started_at=self.started_at,
        )

        self._logger.info(
            "initialized evaluation run %s with %d queries (%s)",
            self.evaluation_run_id,
            metadata.query_count,
            ", ".join(f"{k}={v}" for k, v in distribution.items()),
        )

        return metadata

    def add_query_result(
        self,
        query_id: str,
        metrics: PipelineMetrics,
        failures: Optional[List[FailureRecord]] = None,
    ) -> None:
        """Record results for a query.

        Args:
            query_id: Query identifier.
            metrics: Collected pipeline metrics.
            failures: Any failures encountered (optional).
        """
        self.metrics_collector.record_metric(metrics)

        if failures:
            self._failures.extend(failures)

        self._execution_results.append({
            "query_id": query_id,
            "job_id": metrics.job_id,
            "success": metrics.orchestration_success,
            "metrics": metrics.model_dump(),
            "timestamp": datetime.utcnow().isoformat(),
        })

    def complete(self) -> EvaluationRunMetadata:
        """Mark evaluation run as complete.

        Returns:
            Updated EvaluationRunMetadata.
        """
        self.completed_at = datetime.utcnow()
        duration = (self.completed_at - self.started_at).total_seconds() if self.started_at else 0.0

        succeeded = sum(1 for r in self._execution_results if r.get("success", False))
        failed = sum(1 for r in self._execution_results if not r.get("success", False))

        metadata = EvaluationRunMetadata(
            evaluation_run_id=self.evaluation_run_id,
            dataset_id=self.dataset.dataset_id,
            query_count=len(self._execution_results),
            category_distribution=self.dataset.category_distribution(),
            started_at=self.started_at or datetime.utcnow(),
            completed_at=self.completed_at,
            duration_seconds=duration,
            succeeded_queries=succeeded,
            failed_queries=failed,
            partial_failures=sum(1 for metric in self.metrics_collector.all_metrics() if metric.partial_failure_occurred),
        )

        self._logger.info(
            "evaluation run %s completed in %.1f seconds: %d succeeded, %d failed, %d total failures",
            self.evaluation_run_id,
            duration,
            succeeded,
            failed,
            len(self._failures),
        )

        return metadata

    def get_failures(self) -> List[FailureRecord]:
        """Get all recorded failures.

        Returns:
            List of FailureRecord.
        """
        return self._failures.copy()

    def get_failure_patterns(self) -> Dict[str, Any]:
        """Get analyzed failure patterns.

        Returns:
            Failure pattern analysis.
        """
        return self.failure_analyzer.analyze_failure_patterns(self._failures)

    def get_metrics(self) -> List[PipelineMetrics]:
        """Get all collected metrics.

        Returns:
            List of PipelineMetrics.
        """
        return self.metrics_collector.all_metrics()

    def execution_results(self) -> List[Dict[str, Any]]:
        """Get raw execution results.

        Returns:
            List of query execution results.
        """
        return self._execution_results.copy()
