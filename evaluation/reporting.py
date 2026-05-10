"""Benchmark report generation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Any, List

from shared.logging import get_logger
from evaluation.schemas import EvaluationSummary


class BenchmarkReporter:
    """Generates benchmark reports and summaries."""

    def __init__(self):
        """Initialize benchmark reporter."""
        self._logger = get_logger("evaluation.reporting")

    def generate_json_report(self, summary: EvaluationSummary) -> str:
        """Generate JSON benchmark report.

        Args:
            summary: EvaluationSummary with metrics.

        Returns:
            JSON string.
        """
        report = {
            "evaluation_run_id": summary.evaluation_run_id,
            "dataset_id": summary.dataset_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "total_queries": summary.total_queries,
                "completion_rate": round(summary.completion_rate, 3),
                "latency": {
                    "avg_ms": round(summary.avg_total_latency_ms, 1),
                    "p50_ms": round(summary.p50_latency_ms, 1),
                    "p95_ms": round(summary.p95_latency_ms, 1),
                    "p99_ms": round(summary.p99_latency_ms, 1),
                    "max_ms": round(summary.max_latency_ms, 1),
                },
                "retries": {
                    "avg_count": round(summary.avg_retry_count, 2),
                },
                "failures": {
                    "total": summary.total_failures,
                },
                "provenance": {
                    "avg_coverage": round(summary.avg_provenance_coverage, 3),
                },
                "confidence": {
                    "avg_score": round(summary.avg_confidence_score, 3),
                },
            },
            "by_category": {
                "normal": round(summary.normal_query_success_rate, 3),
                "ambiguous": round(summary.ambiguous_query_success_rate, 3),
                "adversarial": round(summary.adversarial_query_success_rate, 3),
                "contradiction_prone": round(summary.contradiction_query_success_rate, 3),
                "provenance_sensitive": round(summary.provenance_query_success_rate, 3),
            },
        }

        return json.dumps(report, indent=2)

    def generate_markdown_report(self, summary: EvaluationSummary) -> str:
        """Generate markdown benchmark report.

        Args:
            summary: EvaluationSummary with metrics.

        Returns:
            Markdown string.
        """
        lines: List[str] = []

        lines.append("# Evaluation Benchmark Report")
        lines.append("")
        lines.append(f"**Evaluation ID**: `{summary.evaluation_run_id}`")
        lines.append(f"**Dataset**: `{summary.dataset_id}`")
        lines.append(f"**Generated**: {datetime.utcnow().isoformat()}")
        lines.append("")

        # Summary metrics
        lines.append("## Summary Metrics")
        lines.append("")
        lines.append(f"- **Total Queries**: {summary.total_queries}")
        lines.append(f"- **Completion Rate**: {summary.completion_rate * 100:.1f}%")
        lines.append(f"- **Total Failures**: {summary.total_failures}")
        lines.append("")

        # Latency
        lines.append("## Latency Distribution")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Average | {summary.avg_total_latency_ms:.1f} ms |")
        lines.append(f"| P50 | {summary.p50_latency_ms:.1f} ms |")
        lines.append(f"| P95 | {summary.p95_latency_ms:.1f} ms |")
        lines.append(f"| P99 | {summary.p99_latency_ms:.1f} ms |")
        lines.append(f"| Max | {summary.max_latency_ms:.1f} ms |")
        lines.append("")

        # Retries
        lines.append("## Retry Statistics")
        lines.append("")
        lines.append(f"- **Average Retries**: {summary.avg_retry_count:.2f} per query")
        lines.append("")

        # Provenance and Confidence
        lines.append("## Quality Metrics")
        lines.append("")
        lines.append(f"- **Provenance Coverage**: {summary.avg_provenance_coverage * 100:.1f}%")
        lines.append(f"- **Average Confidence Score**: {summary.avg_confidence_score:.3f}")
        lines.append("")

        # Category breakdown
        lines.append("## Performance by Query Category")
        lines.append("")
        lines.append("| Category | Success Rate |")
        lines.append("|----------|--------------|")
        lines.append(f"| Normal | {summary.normal_query_success_rate * 100:.1f}% |")
        lines.append(f"| Ambiguous | {summary.ambiguous_query_success_rate * 100:.1f}% |")
        lines.append(f"| Adversarial | {summary.adversarial_query_success_rate * 100:.1f}% |")
        lines.append(f"| Contradiction-Prone | {summary.contradiction_query_success_rate * 100:.1f}% |")
        lines.append(f"| Provenance-Sensitive | {summary.provenance_query_success_rate * 100:.1f}% |")
        lines.append("")

        return "\n".join(lines)

    def generate_failure_report(
        self,
        failure_patterns: Dict[str, Any],
    ) -> str:
        """Generate markdown failure analysis report.

        Args:
            failure_patterns: Pattern analysis from FailureAnalyzer.

        Returns:
            Markdown string.
        """
        lines: List[str] = []

        lines.append("# Failure Analysis Report")
        lines.append("")
        lines.append(f"**Total Failures**: {failure_patterns.get('total_failures', 0)}")
        lines.append(f"**Recovery Rate**: {failure_patterns.get('recovery_rate', 0) * 100:.1f}%")
        lines.append("")

        lines.append("## Failure Type Distribution")
        lines.append("")

        failure_types = failure_patterns.get("failure_types", {})
        if failure_types:
            lines.append("| Failure Type | Count |")
            lines.append("|--------------|-------|")
            for ftype, count in sorted(failure_types.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| {ftype} | {count} |")
        else:
            lines.append("*No failures detected.*")

        lines.append("")

        lines.append("## Failures by Agent")
        lines.append("")

        by_agent = failure_patterns.get("by_agent", {})
        if by_agent:
            lines.append("| Agent | Failure Count |")
            lines.append("|-------|---------------|")
            for agent, count in sorted(by_agent.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| {agent} | {count} |")
        else:
            lines.append("*No agent-specific failures.*")

        lines.append("")

        lines.append("## Most Common Failure Type")
        lines.append("")
        most_common = failure_patterns.get("most_common_type")
        if most_common:
            count = failure_patterns.get("most_common_count", 0)
            lines.append(f"**{most_common}** ({count} occurrences)")
        else:
            lines.append("*No common failure type.*")

        lines.append("")

        return "\n".join(lines)

    def generate_weak_areas_report(
        self,
        summary: EvaluationSummary,
        failure_patterns: Dict[str, Any],
    ) -> str:
        """Generate report highlighting weak areas and improvement opportunities.

        Args:
            summary: Evaluation summary.
            failure_patterns: Failure pattern analysis.

        Returns:
            Markdown string.
        """
        lines: List[str] = []

        lines.append("# Weak Areas & Improvement Opportunities")
        lines.append("")

        # Low success categories
        lines.append("## Low Success Rate Categories")
        lines.append("")

        categories = {
            "normal": summary.normal_query_success_rate,
            "ambiguous": summary.ambiguous_query_success_rate,
            "adversarial": summary.adversarial_query_success_rate,
            "contradiction_prone": summary.contradiction_query_success_rate,
            "provenance_sensitive": summary.provenance_query_success_rate,
        }

        low_categories = [(k, v) for k, v in categories.items() if v < 0.7]
        if low_categories:
            for cat, rate in sorted(low_categories, key=lambda x: x[1]):
                lines.append(f"- **{cat}**: {rate * 100:.1f}% success rate (below 70% threshold)")
        else:
            lines.append("*All categories above 70% threshold.*")

        lines.append("")

        # High latency
        lines.append("## Latency Concerns")
        lines.append("")

        if summary.p99_latency_ms > 5000:  # 5 second threshold
            lines.append(f"- P99 latency ({summary.p99_latency_ms:.0f} ms) exceeds 5 second threshold")

        if summary.avg_total_latency_ms > 1000:  # 1 second threshold
            lines.append(f"- Average latency ({summary.avg_total_latency_ms:.0f} ms) exceeds 1 second threshold")

        if not (summary.p99_latency_ms > 5000 or summary.avg_total_latency_ms > 1000):
            lines.append("*Latency within acceptable ranges.*")

        lines.append("")

        # High failure rate
        lines.append("## Failure Rate")
        lines.append("")

        failure_rate = summary.total_failures / summary.total_queries if summary.total_queries > 0 else 0.0
        if failure_rate > 0.1:  # 10% threshold
            lines.append(f"- Failure rate ({failure_rate * 100:.1f}%) exceeds 10% threshold")
        else:
            lines.append("*Failure rate within acceptable range.*")

        lines.append("")

        # Low provenance coverage
        lines.append("## Provenance Coverage")
        lines.append("")

        if summary.avg_provenance_coverage < 0.7:
            lines.append(f"- Average provenance coverage ({summary.avg_provenance_coverage * 100:.1f}%) below 70% threshold")
        else:
            lines.append("*Provenance coverage adequate.*")

        lines.append("")

        return "\n".join(lines)
