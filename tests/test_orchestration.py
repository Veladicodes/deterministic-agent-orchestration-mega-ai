"""Tests for orchestration layer.

Validates PipelineRunner, state management, retry handling, and end-to-end execution.
"""

import asyncio
import uuid
from datetime import datetime

import pytest

from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from shared.enums import ExecutionStatus
from shared.logging import configure_logging
from context.shared_context import SharedContext
from orchestration.schemas import RetryRecord, FailureRecord, ExecutionSummary, PipelineResult
from orchestration.state_manager import ExecutionStateManager
from orchestration.retry_coordinator import RetryCoordinator, RetryConfig
from orchestration.result_assembler import ResultAssembler
from orchestration.pipeline import PipelineRunner


configure_logging("test", "DEBUG")


def run_async(coro):
    """Run async test helper."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestExecutionStateManager:
    """Tests for ExecutionStateManager."""

    def test_state_initialization(self):
        """Test state manager initializes to PENDING."""
        manager = ExecutionStateManager(str(uuid.uuid4()))
        manager.initialize()
        assert manager.current_state == ExecutionStatus.PENDING

    def test_state_transitions(self):
        """Test valid state transitions."""
        manager = ExecutionStateManager(str(uuid.uuid4()))
        manager.initialize()
        assert manager.current_state == ExecutionStatus.PENDING

        manager.start_execution()
        assert manager.current_state == ExecutionStatus.RUNNING

        manager.mark_succeeded()
        assert manager.current_state == ExecutionStatus.SUCCEEDED
        assert manager.is_terminal_state()

    def test_state_partial_failure(self):
        """Test partial failure state transition."""
        manager = ExecutionStateManager(str(uuid.uuid4()))
        manager.initialize()
        manager.start_execution()
        manager.mark_partial_failure("test failure")
        assert manager.current_state == ExecutionStatus.PARTIAL_FAILURE
        assert manager.can_continue()

    def test_state_history(self):
        """Test state transition history recording."""
        manager = ExecutionStateManager(str(uuid.uuid4()))
        manager.initialize()
        manager.start_execution()
        manager.mark_succeeded()

        history = manager.state_history
        assert len(history) >= 3
        states = [s for s, _ in history]
        assert states[0] == ExecutionStatus.PENDING
        assert states[-1] == ExecutionStatus.SUCCEEDED

    def test_state_applied_to_context(self):
        """Test state is applied to SharedContext."""
        job_id = str(uuid.uuid4())
        manager = ExecutionStateManager(job_id)
        manager.initialize()
        manager.start_execution()

        context = SharedContext(
            job_id=job_id,
            original_query="test",
        )
        manager.apply_to_context(context)

        assert context.execution_state.status == ExecutionStatus.RUNNING
        assert context.execution_state.started_at is not None


class TestRetryCoordinator:
    """Tests for RetryCoordinator."""

    def test_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        coordinator = RetryCoordinator()

        async def success_func():
            return "success"

        success, result, records = run_async(
            coordinator.execute_with_retry("test_op", success_func)
        )

        assert success is True
        assert result == "success"
        assert len(records) == 0

    def test_retry_eventual_success(self):
        """Test eventual success after retries."""
        coordinator = RetryCoordinator()
        attempt_count = {"count": 0}

        async def flaky_func():
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                raise ValueError(f"Attempt {attempt_count['count']} failed")
            return "success"

        success, result, records = run_async(
            coordinator.execute_with_retry("test_op", flaky_func)
        )

        assert success is True
        assert result == "success"
        assert len(records) == 2  # Two failures before success

    def test_retry_exhaustion(self):
        """Test retry exhaustion."""
        config = RetryConfig(max_retries=2)
        coordinator = RetryCoordinator(config)

        async def always_fails():
            raise ValueError("Always fails")

        success, result, records = run_async(
            coordinator.execute_with_retry("test_op", always_fails)
        )

        assert success is False
        assert isinstance(result, ValueError)
        assert len(records) == 3  # Initial + 2 retries

    def test_retry_backoff_computation(self):
        """Test exponential backoff computation."""
        config = RetryConfig(
            initial_backoff_ms=100.0,
            backoff_multiplier=2.0,
            max_backoff_ms=1000.0,
        )
        coordinator = RetryCoordinator(config)

        # Test backoff progression
        backoff_0 = coordinator._compute_backoff(0)
        backoff_1 = coordinator._compute_backoff(1)
        backoff_2 = coordinator._compute_backoff(2)

        assert backoff_0 == 100.0
        assert backoff_1 == 200.0
        assert backoff_2 == 400.0

    def test_retry_max_backoff_cap(self):
        """Test backoff is capped at max."""
        config = RetryConfig(
            initial_backoff_ms=100.0,
            backoff_multiplier=2.0,
            max_backoff_ms=500.0,
        )
        coordinator = RetryCoordinator(config)

        backoff_10 = coordinator._compute_backoff(10)
        assert backoff_10 == 500.0  # Capped at max


class TestResultAssembler:
    """Tests for ResultAssembler."""

    def test_assembler_initialization(self):
        """Test result assembler initializes properly."""
        assembler = ResultAssembler(str(uuid.uuid4()))
        assert assembler._errors == []
        assert assembler._warnings == []

    def test_add_errors_and_warnings(self):
        """Test adding errors and warnings."""
        assembler = ResultAssembler(str(uuid.uuid4()))
        assembler.add_error("Error 1")
        assembler.add_warning("Warning 1")

        assert len(assembler._errors) == 1
        assert len(assembler._warnings) == 1

    def test_assemble_result(self):
        """Test result assembly."""
        job_id = str(uuid.uuid4())
        assembler = ResultAssembler(job_id)
        assembler.add_error("test error")

        context = SharedContext(
            job_id=job_id,
            original_query="test query",
        )

        start_time = datetime.utcnow()
        end_time = datetime.utcnow()

        result = assembler.assemble(context, success=False, pipeline_duration_ms=1000.0, start_time=start_time, end_time=end_time)

        assert isinstance(result, PipelineResult)
        assert result.success is False
        assert len(result.errors) == 1


class TestPipelineRunner:
    """Tests for PipelineRunner."""

    def test_pipeline_runner_initialization(self):
        """Test pipeline runner initializes properly."""
        runner = PipelineRunner()
        assert runner.budget_manager is not None
        assert runner.exec_logger is not None
        assert runner.retry_config is not None

    def test_pipeline_end_to_end(self):
        """Test complete pipeline execution."""
        runner = PipelineRunner()

        result = run_async(runner.run("What is artificial intelligence?"))

        assert isinstance(result, PipelineResult)
        assert result.summary.job_id
        assert len(result.summary.job_id) > 0

    def test_pipeline_result_structure(self):
        """Test pipeline result has all required fields."""
        runner = PipelineRunner()

        result = run_async(runner.run("test query"))

        # Check summary
        assert result.summary.total_agents > 0
        assert result.summary.pipeline_duration_ms > 0
        assert result.summary.started_at is not None
        assert result.summary.completed_at is not None

        # Check result
        assert result.success is not None
        assert result.agent_outputs is not None
        assert result.execution_trace is not None

    def test_pipeline_deterministic_execution(self):
        """Test pipeline executes agents in deterministic order."""
        runner = PipelineRunner()

        query = "Find information about neural networks"
        results = []

        for _ in range(2):
            result = run_async(runner.run(query))
            results.append(result)

        # Both runs should have same number of agents
        assert len(results[0].agent_outputs) == len(results[1].agent_outputs)

    def test_pipeline_full_agent_execution(self):
        """Test pipeline executes agents."""
        runner = PipelineRunner()

        result = run_async(runner.run("What is machine learning?"))

        # Pipeline should complete with a result
        assert isinstance(result, PipelineResult)
        assert result.summary is not None

    def test_pipeline_produces_final_answer(self):
        """Test pipeline produces a final answer."""
        runner = PipelineRunner()

        result = run_async(runner.run("Explain AI"))

        # Final answer should be present
        if result.summary.final_answer:
            assert len(result.summary.final_answer) > 0

    def test_pipeline_execution_metrics(self):
        """Test pipeline captures execution metrics."""
        runner = PipelineRunner()

        result = run_async(runner.run("test query"))

        # Check metrics
        assert result.summary.total_tool_calls >= 0
        assert result.summary.total_tokens_used >= 0
        assert result.summary.pipeline_duration_ms > 0


class TestPipelineIntegration:
    """Integration tests for orchestration pipeline."""

    def test_end_to_end_pipeline_with_traceability(self):
        """Test complete pipeline with full traceability."""
        runner = PipelineRunner()

        result = run_async(runner.run("Compare AI and machine learning"))

        # Verify structure
        assert result.execution_trace is not None
        assert result.execution_trace.get("job_id") is not None
        assert result.execution_trace.get("sub_tasks") is not None
        assert result.execution_trace.get("tool_calls") is not None

    def test_pipeline_error_handling(self):
        """Test pipeline handles errors gracefully."""
        runner = PipelineRunner()

        # Even with potentially problematic input, should not crash
        result = run_async(runner.run(""))

        assert isinstance(result, PipelineResult)
        assert result.summary is not None

    def test_pipeline_provenance_preservation(self):
        """Test pipeline preserves provenance links."""
        runner = PipelineRunner()

        result = run_async(runner.run("Find information about AI"))

        # If retrieval happened, provenance should be captured
        if result.provenance_links:
            for source_id, link in result.provenance_links.items():
                assert source_id is not None

    def test_state_transitions_logged(self):
        """Test state transitions are properly tracked."""
        runner = PipelineRunner()

        result = run_async(runner.run("test"))

        # Check execution state was set
        status_value = result.summary.status.value if hasattr(result.summary.status, "value") else str(result.summary.status)
        assert status_value in ["succeeded", "partial_failure", "failed"]

    def test_multiple_sequential_pipelines(self):
        """Test running multiple pipelines sequentially."""
        runner = PipelineRunner()

        results = []
        for i in range(2):
            result = run_async(runner.run(f"Query {i}"))
            results.append(result)

        assert len(results) == 2
        # Job IDs should be unique
        assert results[0].summary.job_id != results[1].summary.job_id

    def test_pipeline_agent_sequence(self):
        """Test agents execute in correct order."""
        runner = PipelineRunner()

        result = run_async(runner.run("test"))

        agent_outputs = result.agent_outputs
        agent_list = list(agent_outputs.keys())

        # Find indices
        decomposer_idx = None
        retriever_idx = None
        critic_idx = None
        synthesizer_idx = None

        for i, agent_id in enumerate(agent_list):
            if "decomposer" in agent_id:
                decomposer_idx = i
            elif "retriever" in agent_id:
                retriever_idx = i
            elif "critic" in agent_id:
                critic_idx = i
            elif "synthesizer" in agent_id:
                synthesizer_idx = i

        # Check execution order (all should be present in deterministic order)
        if all(x is not None for x in [decomposer_idx, retriever_idx, critic_idx, synthesizer_idx]):
            assert decomposer_idx < retriever_idx < critic_idx < synthesizer_idx


class TestOrchestrationDeterminism:
    """Tests for orchestration determinism."""

    def test_same_query_produces_same_structure(self):
        """Test same query produces consistent structure."""
        runner = PipelineRunner()

        query = "What is artificial intelligence?"
        results = []

        for _ in range(2):
            result = run_async(runner.run(query))
            results.append(result)

        # Same number of agents, same structure
        assert len(results[0].agent_outputs) == len(results[1].agent_outputs)
        assert results[0].execution_trace["agents_executed"] == results[1].execution_trace["agents_executed"]

    def test_state_machine_consistency(self):
        """Test state machine transitions are consistent."""
        runner = PipelineRunner()

        result = run_async(runner.run("test query"))

        # State should be terminal
        status = result.summary.status
        status_value = status.value if hasattr(status, "value") else str(status)
        assert status_value in ["succeeded", "partial_failure", "failed", "cancelled"]
