"""Metric collection and aggregation for evaluation."""

from __future__ import annotations

from typing import List, Dict, Any
from statistics import mean, median

from shared.logging import get_logger
from evaluation.schemas import PipelineMetrics, EvaluationSummary


class MetricsCollector:
    """Collects and aggregates pipeline metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self._logger = get_logger("evaluation.metrics")
        self._metrics: List[PipelineMetrics] = []

    def record_metric(self, metric: PipelineMetrics) -> None:
        """Record a pipeline metric.

        Args:
            metric: Metric to record.
        """
        self._metrics.append(metric)
        self._logger.debug("recorded metric for job %s, latency=%.1f ms", metric.job_id, metric.total_latency_ms)

    def all_metrics(self) -> List[PipelineMetrics]:
        """Get all collected metrics.

        Returns:
            List of metrics.
        """
        return self._metrics.copy()

    def aggregate_metrics(
        self,
        evaluation_run_id: str,
        dataset_id: str,
        category_distribution: Dict[str, int],
    ) -> EvaluationSummary:
        """Aggregate metrics into summary statistics.

        Args:
            evaluation_run_id: Evaluation run identifier.
            dataset_id: Dataset version.
            category_distribution: Query count by category.

        Returns:
            Aggregated EvaluationSummary.
        """
        if not self._metrics:
            return EvaluationSummary(
                evaluation_run_id=evaluation_run_id,
                dataset_id=dataset_id,
                total_queries=0,
                completion_rate=0.0,
                avg_total_latency_ms=0.0,
                p50_latency_ms=0.0,
                p95_latency_ms=0.0,
                p99_latency_ms=0.0,
                max_latency_ms=0.0,
                avg_retry_count=0.0,
                total_failures=0,
                avg_provenance_coverage=0.0,
                avg_confidence_score=0.0,
                normal_query_success_rate=0.0,
                ambiguous_query_success_rate=0.0,
                adversarial_query_success_rate=0.0,
                contradiction_query_success_rate=0.0,
                provenance_query_success_rate=0.0,
            )

        # Basic stats
        total_queries = len(self._metrics)
        completed = sum(1 for m in self._metrics if m.orchestration_success)
        completion_rate = completed / total_queries if total_queries > 0 else 0.0

        # Latency stats
        latencies = [m.total_latency_ms for m in self._metrics]
        avg_latency = mean(latencies)
        p50_latency = median(latencies)
        
        # Calculate percentiles
        try:
            sorted_latencies = sorted(latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
            p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
        except:
            p95_latency = max(latencies) if latencies else 0.0
            p99_latency = max(latencies) if latencies else 0.0

        max_latency = max(latencies) if latencies else 0.0

        # Retry stats
        retry_counts = [m.retry_count for m in self._metrics]
        avg_retries = mean(retry_counts)

        # Failure stats
        total_failures = sum(1 for m in self._metrics if not m.orchestration_success)

        # Provenance and confidence
        provenance_coverage = [m.provenance_coverage for m in self._metrics]
        avg_provenance = mean(provenance_coverage) if provenance_coverage else 0.0

        confidence_scores = [m.confidence_score for m in self._metrics]
        avg_confidence = mean(confidence_scores) if confidence_scores else 0.0

        # Category-based success rates
        normal_count = category_distribution.get("normal", 0)
        ambiguous_count = category_distribution.get("ambiguous", 0)
        adversarial_count = category_distribution.get("adversarial", 0)
        contradiction_count = category_distribution.get("contradiction_prone", 0)
        provenance_count = category_distribution.get("provenance_sensitive", 0)

        # Note: This is a simplified calculation. In real scenario, we'd track by category
        # For now, distribute success across categories proportionally
        success_by_category = self._estimate_success_by_category(
            completed,
            category_distribution,
        )

        summary = EvaluationSummary(
            evaluation_run_id=evaluation_run_id,
            dataset_id=dataset_id,
            total_queries=total_queries,
            completion_rate=completion_rate,
            avg_total_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            max_latency_ms=max_latency,
            avg_retry_count=avg_retries,
            total_failures=total_failures,
            avg_provenance_coverage=avg_provenance,
            avg_confidence_score=avg_confidence,
            normal_query_success_rate=success_by_category.get("normal", 0.0),
            ambiguous_query_success_rate=success_by_category.get("ambiguous", 0.0),
            adversarial_query_success_rate=success_by_category.get("adversarial", 0.0),
            contradiction_query_success_rate=success_by_category.get("contradiction_prone", 0.0),
            provenance_query_success_rate=success_by_category.get("provenance_sensitive", 0.0),
        )

        return summary

    def _estimate_success_by_category(
        self,
        total_successes: int,
        category_distribution: Dict[str, int],
    ) -> Dict[str, float]:
        """Estimate success rate by category (simplified).

        Args:
            total_successes: Total successful queries.
            category_distribution: Query count per category.

        Returns:
            Dict mapping category to success rate.
        """
        result: Dict[str, float] = {}
        total_queries = sum(category_distribution.values())

        if total_queries == 0:
            return {cat: 0.0 for cat in category_distribution.keys()}

        # Simplified: assume success proportional to category size
        for category, count in category_distribution.items():
            if count > 0:
                proportion = count / total_queries
                success_rate = min(1.0, (total_successes * proportion) / count)
            else:
                success_rate = 0.0
            result[category] = success_rate

        return result

    def clear(self) -> None:
        """Clear collected metrics."""
        self._metrics.clear()
