"""Tests for LLMSynthesizerAgent.

Verifies the LLM-backed synthesizer still returns a schema-conformant
SynthesisOutput, that a mocked LLM tool is invoked and its text used for
the final answer, that budget consumption is recorded (via the same
`tokens` accounting path as any other tool), and that a failing LLM call
falls back to the deterministic base-class synthesis rather than
crashing the pipeline.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from shared.agent_base import AgentConfig
from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from shared.enums import FailureMode
from shared.logging import configure_logging
from shared.tool_base import BaseTool, ToolResult
from context.shared_context import SharedContext, AgentOutput
from agents.schemas import SynthesisOutput
from agents.llm_synthesizer import LLMSynthesizerAgent


configure_logging("test", "DEBUG")


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _StubLLMTool(BaseTool):
    """Deterministic stand-in for LLMTool used in tests."""

    def __init__(self, text: str = "LLM synthesized answer.", tokens: int = 42, success: bool = True):
        super().__init__(name="stub_llm_tool")
        self._text = text
        self._tokens = tokens
        self._success = success

    async def run(self, payload, timeout_seconds=None) -> ToolResult:
        if not self._success:
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, error_message="stubbed failure")
        return ToolResult(
            success=True,
            failure_mode=FailureMode.NONE,
            result={"text": self._text, "tokens": self._tokens, "model": "stub-model", "cost_usd": 0.0001},
        )


@pytest.fixture
def shared_context():
    return SharedContext(job_id=str(uuid.uuid4()), original_query="What is deterministic orchestration?")


@pytest.fixture
def budget_manager():
    return BudgetManager(max_budgets={"synthesizer_test": 1000})


@pytest.fixture
def exec_logger():
    return ExecutionLogger()


def _agent(budget_manager, exec_logger, llm_tool):
    config = AgentConfig(agent_id="synthesizer_test", max_tokens=1000)
    return LLMSynthesizerAgent(config, budget_manager, exec_logger, llm_tool=llm_tool)


def test_llm_synthesizer_returns_schema_conformant_output(shared_context, budget_manager, exec_logger):
    shared_context.agent_outputs.append(
        AgentOutput(agent_id="retriever", output_text="Deterministic orchestration is reproducible.", tokens_used=10)
    )
    agent = _agent(budget_manager, exec_logger, _StubLLMTool())

    result = run_async(agent.run(shared_context))

    assert isinstance(result, SynthesisOutput)
    assert result.final_answer == "LLM synthesized answer."


def test_llm_synthesizer_records_budget_consumption(shared_context, budget_manager, exec_logger):
    shared_context.agent_outputs.append(
        AgentOutput(agent_id="retriever", output_text="Deterministic orchestration is reproducible.", tokens_used=10)
    )
    agent = _agent(budget_manager, exec_logger, _StubLLMTool(tokens=77))

    run_async(agent.run(shared_context))

    assert budget_manager.get_usage("synthesizer_test") == 77


def test_llm_synthesizer_falls_back_to_deterministic_on_llm_failure(shared_context, budget_manager, exec_logger):
    shared_context.agent_outputs.append(
        AgentOutput(agent_id="retriever", output_text="Deterministic orchestration is reproducible.", tokens_used=10)
    )
    agent = _agent(budget_manager, exec_logger, _StubLLMTool(success=False))

    result = run_async(agent.run(shared_context))

    assert isinstance(result, SynthesisOutput)
    assert "Deterministic orchestration is reproducible." in result.final_answer
    assert "LLM synthesis unavailable" in result.final_answer


def test_llm_synthesizer_records_tool_call_with_cost_and_tokens(shared_context, budget_manager, exec_logger):
    shared_context.agent_outputs.append(
        AgentOutput(agent_id="retriever", output_text="Deterministic orchestration is reproducible.", tokens_used=10)
    )
    agent = _agent(budget_manager, exec_logger, _StubLLMTool(tokens=77))

    run_async(agent.run(shared_context))

    llm_calls = [c for c in shared_context.tool_call_log if c.tool_name == "llm_synthesis"]
    assert len(llm_calls) == 1
    assert llm_calls[0].output["tokens"] == 77
    assert llm_calls[0].failure is None


def test_llm_synthesizer_skips_llm_call_when_no_claims(shared_context, budget_manager, exec_logger):
    agent = _agent(budget_manager, exec_logger, _StubLLMTool())

    result = run_async(agent.run(shared_context))

    assert isinstance(result, SynthesisOutput)
    assert result.final_answer == "No information available to synthesize."
    assert budget_manager.get_usage("synthesizer_test") == 0
