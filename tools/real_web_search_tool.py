from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode

TAVILY_ENDPOINT = "https://api.tavily.com/search"


class RealWebSearchTool(BaseTool):
    """Real web search backed by the Tavily search API.

    Design notes:
    - Opt-in only: `RetrieverAgent` still defaults to the deterministic
      `WebSearchTool` stub. This tool is only wired in when
      `Settings.search_backend == "tavily"` (see orchestration/pipeline.py),
      so the existing deterministic test suite and replay guarantees are
      unaffected unless a caller explicitly opts in.
    - Returns results in the exact `result["results"]` shape
      (`title`, `url`, `snippet`, `relevance_score`) that
      `RetrieverAgent._execute_retrieval_hop` already parses from the
      stub tool, so no changes to `agents/retriever.py` are required.
    - `result["tokens"]` is always present (0 for search calls, which have
      no LLM token cost) so `BaseAgent.execute_tool`'s budget accounting
      keeps working unchanged.
    - Non-deterministic by nature (live web results vary run to run); the
      orchestration layer's determinism guarantees apply to control flow,
      retries, and replay-hashing, not to this tool's output content.
    """

    def __init__(self, api_key: Optional[str], name: str | None = None, client: Optional[httpx.AsyncClient] = None):
        super().__init__(name=name)
        self._api_key = api_key
        self.exec_logger = ExecutionLogger()
        self._client = client

    async def run(self, payload: Dict[str, Any], timeout_seconds: Optional[float] = None) -> ToolResult:
        query = (payload or {}).get("query")
        job_id = (payload or {}).get("job_id")
        start = time.perf_counter()
        self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_start", job_id=job_id)

        if not query:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_end", latency=latency, job_id=job_id)
            return ToolResult(success=False, failure_mode=FailureMode.EMPTY, latency_ms=latency, error_message="empty query")

        if not self._api_key:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": "missing_api_key"})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message="search_api_key not configured")

        request_body = {"api_key": self._api_key, "query": query, "max_results": 5}

        try:
            owns_client = self._client is None
            client = self._client or httpx.AsyncClient()
            try:
                response = await client.post(TAVILY_ENDPOINT, json=request_body, timeout=timeout_seconds or 10.0)
            finally:
                if owns_client:
                    await client.aclose()

            latency = (time.perf_counter() - start) * 1000.0

            if response.status_code != 200:
                self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_error", latency=latency, job_id=job_id, extra={"status_code": response.status_code})
                return ToolResult(
                    success=False,
                    failure_mode=FailureMode.INTERNAL,
                    latency_ms=latency,
                    error_message=f"search API returned status {response.status_code}",
                )

            data = response.json()
            raw_results = data.get("results", [])
            if not isinstance(raw_results, list):
                self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": "malformed_response"})
                return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="malformed search response")

            hits = []
            for item in raw_results:
                hits.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                        "relevance_score": float(item.get("score", 0.0)),
                    }
                )

            result_payload = {"results": hits, "tokens": 0}
            tr = ToolResult(success=True, failure_mode=FailureMode.NONE, result=result_payload, latency_ms=latency)
            self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_end", latency=latency, job_id=job_id, extra={"hits": len(hits)})
            return tr

        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_timeout", latency=latency, job_id=job_id)
            return ToolResult(success=False, failure_mode=FailureMode.TIMEOUT, latency_ms=latency, error_message="timeout")
        except Exception as exc:  # pragma: no cover - defensive
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "real_websearch", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": str(exc)})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message=str(exc))
