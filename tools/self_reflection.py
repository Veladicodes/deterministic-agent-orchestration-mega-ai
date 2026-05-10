from __future__ import annotations

import time
from typing import Dict, Any, List

from pydantic import BaseModel

from context.shared_context import SharedContext, AgentOutput, ToolCallRecord
from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode


class ReflectionResult(BaseModel):
    contradictions: bool = False
    contradiction_details: List[str] = []
    total_tool_calls: int = 0
    recent_agents: List[str] = []
    metadata: Dict[str, Any] = {}


class SelfReflectionTool(BaseTool):
    """Analyze the SharedContext to produce lightweight reflections.

    Responsibilities:
    - Inspect previous `AgentOutput`s and `ToolCallRecord`s.
    - Detect simple contradictions (e.g., multiple different final answers).
    - Summarize tool call counts and recent agents involved.
    - Return a small structured payload suitable for downstream policy checks.

    Design notes:
    - The tool accepts either a `SharedContext` instance or a dict-compatible
      mapping. We avoid mutating the context.
    - Contradiction detection is intentionally simple and conservative.
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.exec_logger = ExecutionLogger()

    async def run(self, payload: Dict[str, Any], timeout_seconds: float | None = None) -> ToolResult:
        start = time.time()
        context_obj = payload.get("context") if payload else None
        self.exec_logger.log_event(agent_id=self.name or "reflect", event_type="tool_start", job_id=payload.get("job_id") if payload else None)

        if context_obj is None:
            latency = (time.time() - start) * 1000.0
            return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="missing context")

        # Accept either a SharedContext or raw dict
        if isinstance(context_obj, SharedContext):
            ctx = context_obj
        else:
            try:
                ctx = SharedContext.model_validate(context_obj)
            except Exception as exc:
                latency = (time.time() - start) * 1000.0
                return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message=str(exc))

        contradictions = False
        details: List[str] = []

        # Simple contradiction: multiple different non-empty final answers
        answers = [ao.output_text.strip() for ao in ctx.agent_outputs if ao.output_text and ao.output_text.strip()]
        unique_answers = set(answers)
        if len(unique_answers) > 1:
            contradictions = True
            details.append(f"multiple final answers: {list(unique_answers)[:5]}")

        # Another simple contradiction: same agent produced differing outputs
        agent_map: Dict[str, set] = {}
        for ao in ctx.agent_outputs:
            agent_map.setdefault(ao.agent_id, set()).add((ao.output_text or "").strip())
        for agent_id, outs in agent_map.items():
            outs = {o for o in outs if o}
            if len(outs) > 1:
                contradictions = True
                details.append(f"agent {agent_id} produced multiple outputs: {list(outs)[:5]}")

        total_tool_calls = len(ctx.tool_call_log or [])
        recent_agents = list({ao.agent_id for ao in ctx.agent_outputs})[:10]

        result = ReflectionResult(
            contradictions=contradictions,
            contradiction_details=details,
            total_tool_calls=total_tool_calls,
            recent_agents=recent_agents,
            metadata={"sub_tasks": len(ctx.sub_tasks or [])},
        )

        latency = (time.time() - start) * 1000.0
        self.exec_logger.log_event(agent_id=self.name or "reflect", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"contradictions": contradictions})

        return ToolResult(success=True, failure_mode=FailureMode.NONE, latency_ms=latency, result=result.model_dump())
