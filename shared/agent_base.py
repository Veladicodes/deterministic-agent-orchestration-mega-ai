from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel

from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from shared.logging import get_logger
from shared.tool_base import ToolResult, RetryPolicy, BaseTool
from shared.enums import AgentState


class AgentConfig(BaseModel):
    agent_id: str
    max_tokens: Optional[int] = None


class BaseAgent(ABC):
    """Abstract agent interface.

    Agents should be lightweight adapters that implement `run()` and use
    the provided helpers for tool execution, budget accounting, and logging.
    The class purposefully avoids orchestration logic (scheduling, retries
    across agents) so it can be composed by higher-level orchestrators.
    """

    def __init__(self, config: AgentConfig, budget_manager: BudgetManager, exec_logger: ExecutionLogger):
        self.config = config
        self.budget = budget_manager
        self.exec_logger = exec_logger
        self._state = AgentState.IDLE
        self._logger = get_logger(f"agent.{self.config.agent_id}")

        # Ensure budget exists if configured
        if self.config.max_tokens is not None:
            self.budget.set_budget(self.config.agent_id, int(self.config.max_tokens))

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    @property
    def state(self) -> AgentState:
        return self._state

    async def _run_timed(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            self._state = AgentState.BUSY
            result = await self.run(*args, **kwargs)
            return result
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(
                agent_id=self.agent_id,
                event_type="run_complete",
                latency=elapsed_ms,
                token_count=self.budget.get_usage(self.agent_id),
                job_id=kwargs.get("job_id") or "-",
            )
            self._state = AgentState.IDLE

    @abstractmethod
    async def run(self, shared_context: Any) -> Any:
        """Concrete agents implement domain logic here.

        Keep `run()` focused on a single unit of work and return structured
        outputs; orchestration, retries, and lifecycle management are handled
        by the caller using the provided helpers.
        """
        raise NotImplementedError()

    async def execute_tool(self, tool: BaseTool, payload: Dict[str, Any], retry: Optional[RetryPolicy] = None) -> ToolResult:
        """Helper to execute a tool with optional retry policy and budget tracking.

        Records latency and budget usage and returns the `ToolResult` to the caller.
        """
        retry = retry or RetryPolicy()
        self._logger.debug("executing tool %s payload=%s", tool.name, payload)

        start = time.perf_counter()
        result = await tool.execute_with_retry(payload, retry)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        # Account tokens if result reports them in result payload
        tokens = 0
        if result.result and isinstance(result.result, dict):
            tokens = int(result.result.get("tokens", 0))

        if tokens:
            self.budget.consume(self.agent_id, tokens)

        # Emit structured execution log for the tool event
        self.exec_logger.log_event(
            agent_id=self.agent_id,
            event_type="tool_call",
            latency=elapsed_ms,
            token_count=tokens,
            job_id="-",
            extra={"tool": tool.name, "success": result.success, "failure": result.failure_mode.value},
        )

        return result

    async def retry_helper(self, fn, attempts: int = 1, backoff_seconds: float = 0.0):
        """Small utility to retry a coroutine function from inside an agent.

        This is intentionally minimal; orchestrators may prefer to manage
        concurrency, cancellation, and backoff policies centrally.
        """
        last_exc = None
        for i in range(attempts):
            try:
                return await fn()
            except Exception as exc:  # pragma: no cover - agents will handle specifics
                last_exc = exc
                if backoff_seconds:
                    await asyncio.sleep(backoff_seconds)
        raise last_exc
