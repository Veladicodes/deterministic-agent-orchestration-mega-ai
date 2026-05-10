from __future__ import annotations

import asyncio
import time
from typing import Dict, Any

from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode


class WebSearchTool(BaseTool):
    """A deterministic, stubbed web search tool for local/testing use.

    Design notes:
    - This is a local stub that produces deterministic results from the
      input query; no external HTTP calls are made.
    - The tool enforces a timeout via asyncio.wait_for and reports
      `FailureMode.TIMEOUT` when the timeout is reached.
    - Empty queries are returned as `FailureMode.EMPTY`.
    - The `simulate_malformed` payload flag forces a MALFORMED response
      to exercise downstream error handling.
    - Structured results include `title`, `url`, `snippet`, and
      `relevance_score` for each hit.
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.exec_logger = ExecutionLogger()

    async def _stub_search(self, query: str) -> Dict[str, Any]:
        # Deterministic pseudo-results based on query hash for tests
        await asyncio.sleep(0.05)  # simulate small latency
        hits = []
        base = hash(query) & 0xFFFF
        for i in range(3):
            hits.append(
                {
                    "title": f"Result {i} for {query}",
                    "url": f"https://example.com/{base}/{i}",
                    "snippet": f"Snippet for {query} #{i}",
                    "relevance_score": float(1.0 - i * 0.1),
                }
            )
        return {"results": hits}

    async def run(self, payload: Dict[str, Any], timeout_seconds: float | None = None) -> ToolResult:
        query = (payload or {}).get("query")
        start = time.perf_counter()
        self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_start", job_id=payload.get("job_id") if payload else None)

        if not query:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None)
            return ToolResult(success=False, failure_mode=FailureMode.EMPTY, latency_ms=latency, error_message="empty query")

        if payload.get("simulate_malformed"):
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None)
            return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="malformed simulated")

        try:
            coro = self._stub_search(query)
            if timeout_seconds is not None:
                result_payload = await asyncio.wait_for(coro, timeout_seconds)
            else:
                result_payload = await coro

            latency = (time.perf_counter() - start) * 1000.0
            tr = ToolResult(success=True, failure_mode=FailureMode.NONE, result=result_payload, latency_ms=latency)
            self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"hits": len(result_payload.get("results", []))})
            return tr
        except asyncio.TimeoutError:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_timeout", latency=latency, job_id=payload.get("job_id") if payload else None)
            return ToolResult(success=False, failure_mode=FailureMode.TIMEOUT, latency_ms=latency, error_message="timeout")
        except Exception as exc:  # pragma: no cover - defensive
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "websearch", event_type="tool_error", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"error": str(exc)})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message=str(exc))
