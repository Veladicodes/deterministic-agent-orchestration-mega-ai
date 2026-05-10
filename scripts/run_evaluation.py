#!/usr/bin/env python3
"""
Run a full evaluation on the orchestration system.

Usage:
    python scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation import (
    EvaluationDataset,
    EvaluationRunner,
    BenchmarkReporter,
    PipelineMetrics,
    ExecutionReplayer,
)
from orchestration.pipeline import PipelineRunner
from shared.logging import get_logger

logger = get_logger("eval_cli.run_evaluation")


def create_output_directory(output_dir: Path, evaluation_run_id: str) -> Path:
    """Create output directory for evaluation results."""
    run_dir = output_dir / evaluation_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_results(
    run_dir: Path,
    metadata: Dict[str, Any],
    summary: Dict[str, Any],
    failures: list,
    traces: list,
) -> None:
    """Save evaluation results to output directory."""
    # Save metadata
    with open(run_dir / "metadata.json", "w") as f:
        # Convert datetime to ISO format
        metadata_dict = metadata.copy()
        if isinstance(metadata_dict.get("started_at"), datetime):
            metadata_dict["started_at"] = metadata_dict["started_at"].isoformat()
        if isinstance(metadata_dict.get("completed_at"), datetime):
            metadata_dict["completed_at"] = metadata_dict["completed_at"].isoformat()
        json.dump(metadata_dict, f, indent=2, default=str)

    # Save summary
    with open(run_dir / "summary.json", "w") as f:
        summary_dict = summary.copy()
        if isinstance(summary_dict.get("timestamp"), datetime):
            summary_dict["timestamp"] = summary_dict["timestamp"].isoformat()
        json.dump(summary_dict, f, indent=2, default=str)

    # Save failures
    with open(run_dir / "failures.json", "w") as f:
        failures_data = []
        for failure in failures:
            f_dict = failure.model_dump() if hasattr(failure, "model_dump") else failure
            if isinstance(f_dict.get("timestamp"), datetime):
                f_dict["timestamp"] = f_dict["timestamp"].isoformat()
            failures_data.append(f_dict)
        json.dump(failures_data, f, indent=2, default=str)

    # Save traces (JSONL format)
    with open(run_dir / "traces.jsonl", "w") as f:
        for trace in traces:
            trace_dict = trace.model_dump() if hasattr(trace, "model_dump") else trace
            # Convert datetime fields to ISO format
            if isinstance(trace_dict.get("created_at"), datetime):
                trace_dict["created_at"] = trace_dict["created_at"].isoformat()
            if isinstance(trace_dict.get("replayed_at"), datetime):
                trace_dict["replayed_at"] = trace_dict["replayed_at"].isoformat()
            f.write(json.dumps(trace_dict, default=str) + "\n")

    logger.info(f"Results saved to {run_dir}")


def generate_reports(run_dir: Path, summary: Dict[str, Any], failure_patterns: Dict[str, Any]) -> None:
    """Generate markdown reports."""
    reporter = BenchmarkReporter()

    # Generate main report
    markdown_report = reporter.generate_markdown_report(summary)
    with open(run_dir / "report.md", "w") as f:
        f.write(markdown_report)

    # Generate failure report
    failure_report = reporter.generate_failure_report(failure_patterns)
    with open(run_dir / "failure_report.md", "w") as f:
        f.write(failure_report)

    # Generate weak areas report
    weak_areas_report = reporter.generate_weak_areas_report(summary, failure_patterns)
    with open(run_dir / "weak_areas.md", "w") as f:
        f.write(weak_areas_report)

    logger.info(f"Reports generated in {run_dir}")


def build_metrics_from_result(query_id: str, result: Any, category: str) -> PipelineMetrics:
    """Build evaluation metrics from a real pipeline result."""
    execution_trace = result.execution_trace or {}
    agent_events = execution_trace.get("agent_events", [])

    latencies = {event.get("agent_id"): event.get("latency_ms", 0.0) for event in agent_events}
    tool_calls = execution_trace.get("tool_calls", [])
    summary = result.summary

    return PipelineMetrics(
        job_id=summary.job_id,
        total_latency_ms=summary.pipeline_duration_ms,
        decomposer_latency_ms=float(latencies.get("decomposer", 0.0)),
        retriever_latency_ms=float(latencies.get("retriever", 0.0)),
        critic_latency_ms=float(latencies.get("critic", 0.0)),
        synthesizer_latency_ms=float(latencies.get("synthesizer", 0.0)),
        retry_count=summary.total_retries,
        tool_failure_count=sum(1 for call in tool_calls if not call.get("success", False)),
        partial_failure_occurred=bool(summary.partial_failure),
        completion_rate=1.0 if result.success else 0.0,
        provenance_coverage=1.0 if result.provenance_links else 0.0,
        orchestration_success=bool(result.success),
        decomposition_completeness=1.0 if execution_trace.get("sub_tasks") else 0.0,
        retrieval_relevance_estimate=0.0 if not tool_calls else min(1.0, len([c for c in tool_calls if c.get("success", False)]) / max(len(tool_calls), 1)),
        contradiction_detection_rate=1.0 if result.success else 0.0,
        synthesis_completeness=1.0 if result.final_answer else 0.0,
        confidence_score=0.75 if result.success else 0.25,
        timestamp=datetime.utcnow(),
        metadata={"category": category, "query_id": query_id, "mode": "real_pipeline"},
    )


def build_replay_trace(query_id: str, query: str, result: Any, metrics: PipelineMetrics):
    """Create a deterministic replay trace from a real pipeline result."""
    replayer = ExecutionReplayer()
    execution_trace = result.execution_trace or {}
    agent_sequence = ["decomposer", "retriever", "critic", "synthesizer"]

    start = result.summary.started_at or metrics.timestamp
    end = result.summary.completed_at or metrics.timestamp
    state_transitions = [
        ("INITIALIZED", start),
        ("RUNNING", start),
        ("SUCCEEDED" if result.success else "FAILED", end),
    ]

    execution_path = {
        "deterministic": True,
        "query_id": query_id,
        "category": metrics.metadata.get("category"),
        "success": bool(result.success),
        "pipeline_duration_ms": result.summary.pipeline_duration_ms,
        "agent_events": execution_trace.get("agent_events", []),
    }
    
    # Add routing decisions if available
    if "routing_decisions" in execution_trace:
        execution_path["routing_decisions"] = execution_trace["routing_decisions"]
    if "retrieval_trace" in execution_trace:
        execution_path["retrieval_trace"] = execution_trace["retrieval_trace"]

    trace = replayer.create_trace(
        original_job_id=query_id,
        query=query,
        agent_sequence=agent_sequence,
        tool_calls=execution_trace.get("tool_calls", []),
        state_transitions=state_transitions,
        execution_path=execution_path,
    )

    trace.replayed_at = datetime.utcnow()
    trace.replay_successful = replayer.validate_trace(trace)
    return trace


async def run_evaluation_async(
    dataset: EvaluationDataset, output_dir: Path, verbose: bool = False
) -> None:
    """Run the deterministic pipeline over the evaluation dataset."""
    logger.info(f"Starting evaluation on {dataset.total_entries()} queries")

    runner = EvaluationRunner(dataset)
    runner.initialize()
    pipeline_runner = PipelineRunner()
    replay_traces = []

    for i, entry in enumerate(dataset.all_entries(), 1):
        logger.info(f"Processing query {i}/{dataset.total_entries()}: {entry['query_id']}")

        result = await pipeline_runner.run(entry["input_query"])
        metrics = build_metrics_from_result(entry["query_id"], result, entry.get("category", "unknown"))

        runner.add_query_result(
            query_id=entry["query_id"],
            metrics=metrics,
            failures=[],
        )

        replay_traces.append(build_replay_trace(entry["query_id"], entry["input_query"], result, metrics))

    # Complete run
    completed_metadata = runner.complete()

    # Get results
    all_failures = runner.get_failures()
    summary = runner.metrics_collector.aggregate_metrics(
        evaluation_run_id=runner.evaluation_run_id,
        dataset_id=dataset.dataset_id,
        category_distribution=dataset.category_distribution(),
    )

    # Create output directory
    run_dir = create_output_directory(output_dir, runner.evaluation_run_id)

    # Save results
    save_results(
        run_dir,
        completed_metadata.model_dump() if hasattr(completed_metadata, "model_dump") else completed_metadata,
        summary.model_dump() if hasattr(summary, "model_dump") else summary,
        all_failures,
        replay_traces,
    )

    # Generate reports
    generate_reports(run_dir, summary, runner.get_failure_patterns())

    if verbose:
        logger.info(f"Evaluation complete: {completed_metadata.succeeded_queries}/{completed_metadata.query_count} succeeded")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run evaluation on orchestration system"
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to evaluation dataset (JSON)",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for results",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.dataset.exists():
        logger.error(f"Dataset not found: {args.dataset}")
        sys.exit(1)

    # Load dataset
    try:
        dataset = EvaluationDataset(str(args.dataset))
        dataset.load()
        logger.info(f"Loaded dataset: {dataset.total_entries()} queries")
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        sys.exit(1)

    # Run evaluation
    try:
        asyncio.run(run_evaluation_async(dataset, args.output, verbose=args.verbose))
        logger.info("Evaluation completed successfully")
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
