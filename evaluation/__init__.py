"""Evaluation framework for deterministic pipeline assessment."""

from evaluation.schemas import (
    FailureType,
    PipelineMetrics,
    FailureRecord,
    ReplayTrace,
    EvaluationRunMetadata,
    EvaluationSummary,
)
from evaluation.dataset import EvaluationDataset
from evaluation.metrics import MetricsCollector
from evaluation.failure_analysis import FailureAnalyzer
from evaluation.runner import EvaluationRunner
from evaluation.replay import ExecutionReplayer
from evaluation.reporting import BenchmarkReporter

__all__ = [
    # Schemas
    "FailureType",
    "PipelineMetrics",
    "FailureRecord",
    "ReplayTrace",
    "EvaluationRunMetadata",
    "EvaluationSummary",
    # Components
    "EvaluationDataset",
    "MetricsCollector",
    "FailureAnalyzer",
    "EvaluationRunner",
    "ExecutionReplayer",
    "BenchmarkReporter",
]
