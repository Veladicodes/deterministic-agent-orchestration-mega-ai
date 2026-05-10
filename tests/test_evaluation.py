"""Tests for evaluation framework."""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from evaluation.dataset import EvaluationDataset
from evaluation.metrics import MetricsCollector
from evaluation.failure_analysis import FailureAnalyzer, FailureType
from evaluation.runner import EvaluationRunner
from evaluation.replay import ExecutionReplayer
from evaluation.reporting import BenchmarkReporter
from evaluation.schemas import (
    PipelineMetrics,
    FailureRecord,
    EvaluationRunMetadata,
)


def run_async(coro):
    """Run async code in tests."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestEvaluationDataset:
    """Tests for EvaluationDataset."""

    def test_dataset_loads(self):
        """Test dataset loading."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        assert dataset.total_entries() > 0
        assert len(dataset.all_entries()) > 0

    def test_dataset_metadata(self):
        """Test dataset metadata access."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        assert dataset.dataset_id
        assert "v1" in dataset.dataset_id or "1" in dataset.dataset_id

    def test_dataset_categories(self):
        """Test category filtering."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        normal = dataset.entries_by_category("normal")
        assert len(normal) > 0

        ambiguous = dataset.entries_by_category("ambiguous")
        assert len(ambiguous) > 0

        distribution = dataset.category_distribution()
        assert "normal" in distribution
        assert "ambiguous" in distribution

    def test_dataset_entry_retrieval(self):
        """Test individual entry retrieval."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        entries = dataset.all_entries()
        if entries:
            first = entries[0]
            query_id = first.get("query_id")

            retrieved = dataset.get_entry(query_id)
            assert retrieved is not None
            assert retrieved.get("query_id") == query_id


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_record_metrics(self):
        """Test recording metrics."""
        collector = MetricsCollector()

        metric = PipelineMetrics(
            job_id="test_job_001",
            total_latency_ms=1500.5,
            decomposer_latency_ms=100.0,
            retriever_latency_ms=800.0,
            critic_latency_ms=300.0,
            synthesizer_latency_ms=300.5,
            retry_count=2,
            completion_rate=0.9,
        )

        collector.record_metric(metric)
        assert len(collector.all_metrics()) == 1

    def test_aggregate_metrics(self):
        """Test metric aggregation."""
        collector = MetricsCollector()

        # Add multiple metrics
        for i in range(5):
            metric = PipelineMetrics(
                job_id=f"test_job_{i:03d}",
                total_latency_ms=1000.0 + i * 100,
                retry_count=i,
                completion_rate=0.8 + i * 0.04,
                provenance_coverage=0.7,
                confidence_score=0.8,
            )
            collector.record_metric(metric)

        summary = collector.aggregate_metrics(
            evaluation_run_id="eval_001",
            dataset_id="dataset_v1",
            category_distribution={"normal": 5},
        )

        assert summary.total_queries == 5
        assert summary.avg_total_latency_ms > 0
        assert summary.p50_latency_ms > 0


class TestFailureAnalyzer:
    """Tests for FailureAnalyzer."""

    def test_classify_retrieval_failure(self):
        """Test retrieval failure classification."""
        analyzer = FailureAnalyzer()

        ftype = analyzer.classify_failure(
            job_id="job_001",
            agent_id="retriever",
            error_message="No results returned from search",
            context={},
        )

        assert ftype == FailureType.RETRIEVAL_FAILURE

    def test_classify_timeout_failure(self):
        """Test timeout failure classification."""
        analyzer = FailureAnalyzer()

        ftype = analyzer.classify_failure(
            job_id="job_001",
            agent_id="retriever",
            error_message="Request timeout exceeded",
            context={},
        )

        assert ftype == FailureType.TIMEOUT_FAILURE

    def test_classify_synthesis_failure(self):
        """Test synthesis failure classification."""
        analyzer = FailureAnalyzer()

        # Test with low confidence - should classify as LOW_CONFIDENCE_SYNTHESIS
        ftype = analyzer.classify_failure(
            job_id="job_001",
            agent_id="synthesizer",
            error_message="Synthesis low confidence",
            context={"confidence_score": 0.1, "provenance_count": 5},
        )

        assert ftype == FailureType.LOW_CONFIDENCE_SYNTHESIS

    def test_create_failure_record(self):
        """Test creating failure records."""
        analyzer = FailureAnalyzer()

        record = analyzer.create_failure_record(
            failure_id=str(uuid.uuid4()),
            job_id="job_001",
            agent_id="retriever",
            error_message="Retrieval timeout",
            context={"phase": "retrieve"},
        )

        assert record.failure_id
        assert record.job_id == "job_001"
        assert record.agent_id == "retriever"

    def test_analyze_failure_patterns(self):
        """Test failure pattern analysis."""
        analyzer = FailureAnalyzer()

        failures = [
            FailureRecord(
                failure_id=str(uuid.uuid4()),
                job_id="job_001",
                failure_type=FailureType.RETRIEVAL_FAILURE,
                agent_id="retriever",
            ),
            FailureRecord(
                failure_id=str(uuid.uuid4()),
                job_id="job_002",
                failure_type=FailureType.RETRIEVAL_FAILURE,
                agent_id="retriever",
            ),
            FailureRecord(
                failure_id=str(uuid.uuid4()),
                job_id="job_003",
                failure_type=FailureType.TIMEOUT_FAILURE,
                agent_id="synthesizer",
            ),
        ]

        patterns = analyzer.analyze_failure_patterns(failures)

        assert patterns["total_failures"] == 3
        assert "retrieval_failure" in patterns["failure_types"]
        assert patterns["failure_types"]["retrieval_failure"] == 2


class TestEvaluationRunner:
    """Tests for EvaluationRunner."""

    def test_runner_initialization(self):
        """Test runner initialization."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        runner = EvaluationRunner(dataset)
        metadata = runner.initialize()

        assert metadata.evaluation_run_id
        assert metadata.query_count > 0
        assert runner.started_at

    def test_runner_add_results(self):
        """Test adding results to runner."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        runner = EvaluationRunner(dataset)
        runner.initialize()

        metric = PipelineMetrics(
            job_id="test_job_001",
            total_latency_ms=1000.0,
        )

        runner.add_query_result("normal_001", metric, failures=None)

        assert len(runner.get_metrics()) == 1

    def test_runner_completion(self):
        """Test runner completion."""
        dataset = EvaluationDataset("data/evaluation_dataset.json")
        dataset.load()

        runner = EvaluationRunner(dataset)
        runner.initialize()

        metric = PipelineMetrics(
            job_id="test_job_001",
            total_latency_ms=1000.0,
            orchestration_success=True,
        )

        runner.add_query_result("normal_001", metric)
        metadata = runner.complete()

        assert metadata.completed_at
        assert metadata.duration_seconds >= 0
        assert metadata.succeeded_queries == 1


class TestExecutionReplayer:
    """Tests for ExecutionReplayer."""

    def test_create_trace(self):
        """Test creating execution trace."""
        replayer = ExecutionReplayer()

        trace = replayer.create_trace(
            original_job_id="job_001",
            query="test query",
            agent_sequence=["decomposer", "retriever", "critic", "synthesizer"],
            tool_calls=[],
            state_transitions=[("RUNNING", datetime.utcnow()), ("SUCCEEDED", datetime.utcnow())],
            execution_path={"deterministic": True},
        )

        assert trace.original_job_id == "job_001"
        assert len(trace.agent_sequence) == 4

    def test_validate_trace(self):
        """Test trace validation."""
        replayer = ExecutionReplayer()

        trace = replayer.create_trace(
            original_job_id="job_001",
            query="test",
            agent_sequence=["decomposer", "synthesizer"],
            tool_calls=[],
            state_transitions=[("RUNNING", datetime.utcnow()), ("SUCCEEDED", datetime.utcnow())],
            execution_path={"deterministic": True, "agents": ["decomposer", "synthesizer"]},
        )

        assert replayer.validate_trace(trace)

    def test_compare_traces(self):
        """Test trace comparison."""
        replayer = ExecutionReplayer()

        trace1 = replayer.create_trace(
            original_job_id="job_001",
            query="test",
            agent_sequence=["decomposer", "synthesizer"],
            tool_calls=[{"id": "tool_1"}],
            state_transitions=[("RUNNING", datetime.utcnow())],
            execution_path={},
        )

        trace2 = replayer.create_trace(
            original_job_id="job_002",
            query="test",
            agent_sequence=["decomposer", "synthesizer"],
            tool_calls=[{"id": "tool_1"}],
            state_transitions=[("RUNNING", datetime.utcnow())],
            execution_path={},
        )

        comparison = replayer.compare_traces(trace1, trace2)
        assert comparison["identical"]

    def test_trace_hash_consistency(self):
        """Test deterministic trace hashes for identical execution content."""
        replayer = ExecutionReplayer()

        trace1 = replayer.create_trace(
            original_job_id="job_001",
            query="test",
            agent_sequence=["decomposer", "synthesizer"],
            tool_calls=[{"id": "tool_1", "result": "ok"}],
            state_transitions=[("RUNNING", datetime.utcnow()), ("SUCCEEDED", datetime.utcnow())],
            execution_path={"deterministic": True},
        )

        trace2 = replayer.create_trace(
            original_job_id="job_002",
            query="test",
            agent_sequence=["decomposer", "synthesizer"],
            tool_calls=[{"id": "tool_1", "result": "ok"}],
            state_transitions=[("RUNNING", trace1.state_transitions[0][1]), ("SUCCEEDED", trace1.state_transitions[1][1])],
            execution_path={"deterministic": True},
        )

        assert trace1.execution_hash == trace2.execution_hash
        assert replayer.validate_trace(trace1)
        assert replayer.validate_trace(trace2)

        summary = replayer.replay_summary(trace1)
        assert summary["integrity_valid"]
        assert summary["execution_hash"] == trace1.execution_hash


class TestBenchmarkReporter:
    """Tests for BenchmarkReporter."""

    def test_json_report_generation(self):
        """Test JSON report generation."""
        from evaluation.schemas import EvaluationSummary

        reporter = BenchmarkReporter()

        summary = EvaluationSummary(
            evaluation_run_id="eval_001",
            dataset_id="dataset_v1",
            total_queries=100,
            completion_rate=0.95,
            avg_total_latency_ms=1500.0,
            p50_latency_ms=1000.0,
            p95_latency_ms=3000.0,
            p99_latency_ms=4500.0,
            max_latency_ms=5000.0,
            avg_retry_count=0.5,
            total_failures=5,
            avg_provenance_coverage=0.85,
            avg_confidence_score=0.80,
            normal_query_success_rate=0.95,
            ambiguous_query_success_rate=0.70,
            adversarial_query_success_rate=0.60,
            contradiction_query_success_rate=0.75,
            provenance_query_success_rate=0.80,
        )

        report = reporter.generate_json_report(summary)
        assert "eval_001" in report
        assert "1500" in report or "1500.0" in report

    def test_markdown_report_generation(self):
        """Test markdown report generation."""
        from evaluation.schemas import EvaluationSummary

        reporter = BenchmarkReporter()

        summary = EvaluationSummary(
            evaluation_run_id="eval_001",
            dataset_id="dataset_v1",
            total_queries=100,
            completion_rate=0.95,
            avg_total_latency_ms=1500.0,
            p50_latency_ms=1000.0,
            p95_latency_ms=3000.0,
            p99_latency_ms=4500.0,
            max_latency_ms=5000.0,
            avg_retry_count=0.5,
            total_failures=5,
            avg_provenance_coverage=0.85,
            avg_confidence_score=0.80,
            normal_query_success_rate=0.95,
            ambiguous_query_success_rate=0.70,
            adversarial_query_success_rate=0.60,
            contradiction_query_success_rate=0.75,
            provenance_query_success_rate=0.80,
        )

        report = reporter.generate_markdown_report(summary)
        assert "Evaluation Benchmark Report" in report
        assert "Summary Metrics" in report
        assert "100" in report
