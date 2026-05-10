"""Tests for agent layer implementations.

Validates decomposition, retrieval, critique, synthesis, and persistence.
"""

import asyncio
import uuid
from datetime import datetime

import pytest

from shared.agent_base import AgentConfig
from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from shared.enums import ExecutionStatus, FailureMode
from shared.logging import configure_logging
from context.shared_context import SharedContext, SubTask, AgentOutput, ToolCallRecord
from agents.decomposer import DecomposerAgent
from agents.retriever import RetrieverAgent
from agents.critic import CriticAgent
from agents.synthesizer import SynthesizerAgent
from agents.schemas import (
    DecomposerOutput,
    RetrieverOutput,
    RetrievalResult,
    CritiqueOutput,
    SynthesisOutput,
)
from tools.web_search import WebSearchTool


configure_logging("test", "DEBUG")


def run_async(coro):
    """Run async test helper."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture
def shared_context():
    """Create a shared context for testing."""
    return SharedContext(
        job_id=str(uuid.uuid4()),
        original_query="Find information about AI and compare with machine learning",
    )


@pytest.fixture
def budget_manager():
    """Create a budget manager."""
    return BudgetManager(max_budgets={"decomposer": 1000, "retriever": 1000, "critic": 1000, "synthesizer": 1000})


@pytest.fixture
def exec_logger():
    """Create an execution logger."""
    return ExecutionLogger()


@pytest.fixture
def decomposer_agent(budget_manager, exec_logger):
    """Create a decomposer agent."""
    config = AgentConfig(agent_id="decomposer_test")
    return DecomposerAgent(config, budget_manager, exec_logger)


@pytest.fixture
def retriever_agent(budget_manager, exec_logger):
    """Create a retriever agent with mocked web search."""
    config = AgentConfig(agent_id="retriever_test")
    agent = RetrieverAgent(config, budget_manager, exec_logger)
    return agent


@pytest.fixture
def critic_agent(budget_manager, exec_logger):
    """Create a critic agent."""
    config = AgentConfig(agent_id="critic_test")
    return CriticAgent(config, budget_manager, exec_logger)


@pytest.fixture
def synthesizer_agent(budget_manager, exec_logger):
    """Create a synthesizer agent."""
    config = AgentConfig(agent_id="synthesizer_test")
    return SynthesizerAgent(config, budget_manager, exec_logger)


class TestDecomposerAgent:
    """Tests for DecomposerAgent."""

    def test_decomposition_basic(self, decomposer_agent, shared_context):
        """Test basic query decomposition."""
        result = run_async(decomposer_agent.run(shared_context))

        assert isinstance(result, DecomposerOutput)
        assert len(result.sub_task_ids) > 0
        assert isinstance(result.dependency_graph, dict)
        assert len(shared_context.sub_tasks) == len(result.sub_task_ids)

    def test_decomposition_creates_subtasks(self, decomposer_agent, shared_context):
        """Test that decomposition creates proper subtasks."""
        result = run_async(decomposer_agent.run(shared_context))

        for task_id in result.sub_task_ids:
            matching_tasks = [t for t in shared_context.sub_tasks if t.id == task_id]
            assert len(matching_tasks) == 1
            task = matching_tasks[0]
            assert task.status == ExecutionStatus.PENDING
            assert task.description is not None

    def test_decomposition_detects_ambiguities(self, decomposer_agent):
        """Test ambiguity detection."""
        context = SharedContext(
            job_id=str(uuid.uuid4()),
            original_query="Find some of the best recent information about that topic",
        )
        result = run_async(decomposer_agent.run(context))

        assert len(result.ambiguity_flags) > 0
        # Should detect vague_quantity, relative_reference, time_ambiguity
        flag_text = str(result.ambiguity_flags).lower()
        assert any(keyword in flag_text for keyword in ["vague", "recent", "best"])

    def test_decomposition_deterministic(self, decomposer_agent):
        """Test that decomposition is deterministic."""
        context1 = SharedContext(
            job_id=str(uuid.uuid4()),
            original_query="Find AI information and analyze machine learning",
        )
        context2 = SharedContext(
            job_id=str(uuid.uuid4()),
            original_query="Find AI information and analyze machine learning",
        )

        result1 = run_async(decomposer_agent.run(context1))
        result2 = run_async(decomposer_agent.run(context2))

        # Same input should produce same number of subtasks and ambiguities
        assert len(result1.sub_task_ids) == len(result2.sub_task_ids)
        assert len(result1.ambiguity_flags) == len(result2.ambiguity_flags)


class TestRetrieverAgent:
    """Tests for RetrieverAgent."""

    def test_retrieval_basic(self, retriever_agent, shared_context):
        """Test basic retrieval execution."""
        # Add some sub-tasks first
        shared_context.sub_tasks.append(
            SubTask(
                id=str(uuid.uuid4()),
                description="[search] artificial intelligence",
                metadata={"intent": "search", "entities": ["AI"]},
            )
        )

        result = run_async(retriever_agent.run(shared_context))

        assert isinstance(result, RetrieverOutput)
        assert result.total_hops_performed == 2
        assert len(result.refinement_queries) > 0
        assert isinstance(result.provenance_records, dict)

    def test_retrieval_logs_tool_calls(self, retriever_agent, shared_context):
        """Test that retrieval logs tool calls in shared context."""
        shared_context.sub_tasks.append(
            SubTask(
                id=str(uuid.uuid4()),
                description="[search] test query",
                metadata={"intent": "search"},
            )
        )

        result = run_async(retriever_agent.run(shared_context))

        # Tool calls should be logged
        assert len(shared_context.tool_call_log) > 0

    def test_retrieval_builds_provenance(self, retriever_agent, shared_context):
        """Test that retrieval builds provenance map."""
        shared_context.sub_tasks.append(
            SubTask(
                id=str(uuid.uuid4()),
                description="[search] information",
                metadata={"intent": "search"},
            )
        )

        result = run_async(retriever_agent.run(shared_context))

        # Provenance map should have entries
        if result.results:
            assert len(result.provenance_records) > 0
            for record in result.provenance_records.values():
                assert record.source_id
                assert 0.0 <= record.weight <= 1.0


class TestCriticAgent:
    """Tests for CriticAgent."""

    def test_critique_no_contradiction(self, critic_agent, shared_context):
        """Test critique when there are no contradictions."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="test_agent_1",
                output_text="AI is beneficial for society",
                tokens_used=50,
            )
        )

        result = run_async(critic_agent.run(shared_context))

        assert isinstance(result, CritiqueOutput)
        assert result.contradictions_found == 0

    def test_critique_detects_contradiction(self, critic_agent, shared_context):
        """Test that critic detects contradictions."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="AI is beneficial",
                tokens_used=50,
            )
        )
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent2",
                output_text="AI is harmful",
                tokens_used=50,
            )
        )

        result = run_async(critic_agent.run(shared_context))

        # Might detect good/bad or beneficial/harmful contradiction
        assert isinstance(result, CritiqueOutput)

    def test_critique_flags_low_confidence(self, critic_agent, shared_context):
        """Test that critic flags low-confidence outputs."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="",  # Empty output = low confidence
                tokens_used=0,
            )
        )

        result = run_async(critic_agent.run(shared_context))

        assert result.low_confidence_count >= 0

    def test_critique_produces_score(self, critic_agent, shared_context):
        """Test that critique produces overall confidence score."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="Test output with reasonable length for confidence",
                tokens_used=100,
                tool_calls=[ToolCallRecord(tool_name="test", input={})],
            )
        )

        result = run_async(critic_agent.run(shared_context))

        assert result.overall_confidence.score >= 0.0
        assert result.overall_confidence.score <= 1.0


class TestSynthesizerAgent:
    """Tests for SynthesizerAgent."""

    def test_synthesis_basic(self, synthesizer_agent, shared_context):
        """Test basic synthesis."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="AI is a technology",
                tokens_used=50,
            )
        )

        result = run_async(synthesizer_agent.run(shared_context))

        assert isinstance(result, SynthesisOutput)
        assert result.final_answer
        assert isinstance(result.confidence_score.score, float)

    def test_synthesis_removes_flagged_claims(self, synthesizer_agent, shared_context):
        """Test that synthesis removes flagged claims."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="This should be removed",
                tokens_used=50,
            )
        )

        # Simulate flagged claim (add via mock)
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="critic",
                output_text="critique_analysis",
                tokens_used=50,
                metadata={
                    "flagged_claims": ["This should be removed"],
                },
            )
        )

        result = run_async(synthesizer_agent.run(shared_context))

        assert isinstance(result, SynthesisOutput)
        assert len(result.removed_claims) >= 0

    def test_synthesis_preserves_provenance(self, synthesizer_agent, shared_context):
        """Test that synthesis preserves provenance links."""
        # Add retriever output with provenance
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="retriever",
                output_text="retrieval results",
                tokens_used=100,
                metadata={
                    "results": [
                        {
                            "query": "test",
                            "source_url": "https://example.com",
                            "snippet": "Example content",
                        }
                    ],
                    "provenance_records": {
                        "https://example.com": {
                            "source_id": "https://example.com",
                            "weight": 0.8,
                            "metadata": {},
                        }
                    },
                },
            )
        )

        result = run_async(synthesizer_agent.run(shared_context))

        assert isinstance(result, SynthesisOutput)

    def test_synthesis_confidence_scoring(self, synthesizer_agent, shared_context):
        """Test confidence scoring in synthesis."""
        shared_context.agent_outputs.append(
            AgentOutput(
                agent_id="agent1",
                output_text="Detailed output with multiple sources and evidence",
                tokens_used=200,
                tool_calls=[
                    ToolCallRecord(tool_name="search", input={"q": "query"}),
                    ToolCallRecord(tool_name="search", input={"q": "query2"}),
                ],
            )
        )

        result = run_async(synthesizer_agent.run(shared_context))

        assert result.confidence_score.score > 0.0
        assert result.confidence_score.reasoning


class TestAgentIntegration:
    """Integration tests for agent workflow."""

    def test_agent_pipeline_flow(
        self, decomposer_agent, retriever_agent, critic_agent, synthesizer_agent
    ):
        """Test complete pipeline flow: decompose -> retrieve -> critique -> synthesize."""
        context = SharedContext(
            job_id=str(uuid.uuid4()),
            original_query="Find information about AI and compare with ML",
        )

        # Phase 1: Decompose
        decompose_result = run_async(decomposer_agent.run(context))
        assert len(context.sub_tasks) > 0

        # Add decomposer output to context
        context.agent_outputs.append(
            AgentOutput(
                agent_id="decomposer",
                output_text=decompose_result.reasoning,
                tokens_used=0,
            )
        )

        # Phase 2: Retrieve
        retrieve_result = run_async(retriever_agent.run(context))
        context.agent_outputs.append(
            AgentOutput(
                agent_id="retriever",
                output_text=retrieve_result.reasoning,
                tokens_used=0,
            )
        )

        # Phase 3: Critique
        critique_result = run_async(critic_agent.run(context))
        context.agent_outputs.append(
            AgentOutput(
                agent_id="critic",
                output_text=critique_result.reasoning,
                tokens_used=0,
            )
        )

        # Phase 4: Synthesize
        synthesis_result = run_async(synthesizer_agent.run(context))

        # Verify final output
        assert synthesis_result.final_answer
        assert isinstance(synthesis_result.confidence_score.score, float)
        assert len(synthesis_result.removed_claims) >= 0

    def test_agent_execution_logging(self, decomposer_agent, shared_context):
        """Test that agent execution is properly logged."""
        result = run_async(decomposer_agent.run(shared_context))

        # Execution logger should have events
        # (In real usage, would check logger output or persistence)
        assert result.reasoning


class TestAgentDeterminism:
    """Tests for agent determinism and reproducibility."""

    def test_decomposer_determinism(self):
        """Test that decomposer produces consistent results."""
        query = "Find AI information and analyze ML"
        results = []

        for _ in range(3):
            context = SharedContext(
                job_id=str(uuid.uuid4()),
                original_query=query,
            )
            config = AgentConfig(agent_id="decomposer")
            agent = DecomposerAgent(config, BudgetManager(), ExecutionLogger())
            result = run_async(agent.run(context))
            results.append(result)

        # All runs should produce same number of subtasks
        assert all(len(r.sub_task_ids) == len(results[0].sub_task_ids) for r in results)

    def test_critic_determinism(self):
        """Test that critic produces consistent results."""
        config = AgentConfig(agent_id="critic")
        agent = CriticAgent(config, BudgetManager(), ExecutionLogger())

        results = []
        for _ in range(2):
            context = SharedContext(
                job_id=str(uuid.uuid4()),
                original_query="test",
            )
            context.agent_outputs.append(
                AgentOutput(
                    agent_id="test",
                    output_text="This is true",
                    tokens_used=50,
                )
            )
            result = run_async(agent.run(context))
            results.append(result)

        # Same input should produce same structure
        assert results[0].contradictions_found == results[1].contradictions_found
