import asyncio
import time
from typing import Dict, Any

import pytest

from tools.web_search import WebSearchTool
from tools.code_execution import CodeExecutionTool
from tools.db_lookup import DatabaseLookupTool
from tools.self_reflection import SelfReflectionTool
from shared.tool_base import ToolResult, RetryPolicy, BaseTool
from shared.enums import FailureMode
from context.shared_context import SharedContext, AgentOutput, ToolCallRecord


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_web_search_success():
    tool = WebSearchTool("web")
    r = run_async(tool.run({"query": "test"}, timeout_seconds=1.0))
    assert isinstance(r, ToolResult)
    assert r.success is True
    assert r.result and "results" in r.result


def test_web_search_empty():
    tool = WebSearchTool("web")
    r = run_async(tool.run({"query": ""}, timeout_seconds=1.0))
    assert r.success is False
    assert r.failure_mode == FailureMode.EMPTY


def test_web_search_timeout():
    tool = WebSearchTool("web")
    # simulate long running by using very small timeout
    r = run_async(tool.run({"query": "long"}, timeout_seconds=0.0001))
    assert r.success is False
    assert r.failure_mode in (FailureMode.TIMEOUT, FailureMode.INTERNAL)


def test_code_execution_success():
    tool = CodeExecutionTool("ce")
    r = run_async(tool.run({"code": "print('hello')"}, timeout_seconds=2.0))
    assert r.success is True
    assert "stdout" in r.result and "hello" in r.result["stdout"]


def test_code_execution_malformed():
    tool = CodeExecutionTool("ce")
    r = run_async(tool.run({"bad": True}, timeout_seconds=1.0))
    assert r.success is False
    assert r.failure_mode == FailureMode.MALFORMED


def test_code_execution_timeout():
    tool = CodeExecutionTool("ce")
    # Sleep in code to trigger timeout
    r = run_async(tool.run({"code": "import time; time.sleep(1)"}, timeout_seconds=0.01))
    assert r.success is False
    assert r.failure_mode == FailureMode.TIMEOUT


def test_db_lookup_malformed():
    tool = DatabaseLookupTool("db")
    r = run_async(tool.run({"sql": "DROP TABLE users;"}, timeout_seconds=1.0))
    assert r.success is False
    assert r.failure_mode == FailureMode.MALFORMED


def test_self_reflection_contradiction():
    # Build a SharedContext with conflicting agent outputs
    ctx = SharedContext(
        job_id="job1",
        original_query="why",
        agent_outputs=[
            AgentOutput(agent_id="a1", output_text="Answer A", tokens_used=10),
            AgentOutput(agent_id="a2", output_text="Answer B", tokens_used=12),
        ],
        tool_call_log=[ToolCallRecord(tool_name="t1")],
    )
    tool = SelfReflectionTool("refl")
    r = run_async(tool.run({"context": ctx}, timeout_seconds=1.0))
    assert r.success is True
    assert r.result and r.result.get("contradictions") is True


def test_retry_behavior():
    # Create a small test tool that fails once then succeeds
    class FlakyTool(BaseTool):
        def __init__(self):
            super().__init__("flaky")
            self._calls = 0

        async def run(self, payload: Dict[str, Any], timeout_seconds: float | None = None) -> ToolResult:
            self._calls += 1
            if self._calls == 1:
                raise RuntimeError("transient")
            return ToolResult(success=True, result={"ok": True})

    t = FlakyTool()
    # Single retry allowed -> should succeed
    rp = RetryPolicy(max_retries=1, backoff_seconds=0)
    r = run_async(t.execute_with_retry({}, rp))
    assert isinstance(r, ToolResult)
    assert r.success is True
