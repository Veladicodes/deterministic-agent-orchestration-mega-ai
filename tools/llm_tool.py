from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Approximate list price for Claude Haiku, used only to surface a rough
# cost estimate alongside token counts. Not billing-accurate; update if
# the configured model or pricing changes.
_INPUT_COST_PER_MTOK = 0.80
_OUTPUT_COST_PER_MTOK = 4.00


class LLMTool(BaseTool):
    """Real LLM completion backed by the Anthropic Messages API.

    Design notes:
    - Opt-in only: selected by `LLMSynthesizerAgent`, itself only wired in
      when `Settings.synthesizer_backend == "llm"` (see
      orchestration/pipeline.py). The deterministic `SynthesizerAgent`
      remains the default.
    - Returns `result["tokens"]` (total input+output tokens) so
      `BaseAgent.execute_tool` automatically records real token cost
      against the agent's budget with zero changes to `shared/budget.py`.
    - `result["cost_usd"]` is a rough estimate for observability/reporting;
      it is not used by budget accounting, which only reads `tokens`.
    """

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "claude-haiku-4-5-20251001",
        name: str | None = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(name=name)
        self._api_key = api_key
        self._model = model
        self.exec_logger = ExecutionLogger()
        self._client = client

    async def run(self, payload: Dict[str, Any], timeout_seconds: Optional[float] = None) -> ToolResult:
        prompt = (payload or {}).get("prompt")
        job_id = (payload or {}).get("job_id")
        max_tokens = int((payload or {}).get("max_tokens", 512))
        start = time.perf_counter()
        self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_start", job_id=job_id)

        if not prompt:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_end", latency=latency, job_id=job_id)
            return ToolResult(success=False, failure_mode=FailureMode.EMPTY, latency_ms=latency, error_message="empty prompt")

        if not self._api_key:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": "missing_api_key"})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message="anthropic_api_key not configured")

        request_body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            owns_client = self._client is None
            client = self._client or httpx.AsyncClient()
            try:
                response = await client.post(ANTHROPIC_ENDPOINT, json=request_body, headers=headers, timeout=timeout_seconds or 30.0)
            finally:
                if owns_client:
                    await client.aclose()

            latency = (time.perf_counter() - start) * 1000.0

            if response.status_code != 200:
                self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_error", latency=latency, job_id=job_id, extra={"status_code": response.status_code})
                return ToolResult(
                    success=False,
                    failure_mode=FailureMode.INTERNAL,
                    latency_ms=latency,
                    error_message=f"LLM API returned status {response.status_code}",
                )

            data = response.json()
            content_blocks = data.get("content", [])
            if not isinstance(content_blocks, list) or not content_blocks:
                self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": "malformed_response"})
                return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="malformed LLM response")

            text = "".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
            usage = data.get("usage", {}) or {}
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            total_tokens = input_tokens + output_tokens
            cost_usd = (input_tokens / 1_000_000) * _INPUT_COST_PER_MTOK + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_MTOK

            result_payload = {
                "text": text,
                "tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": self._model,
                "cost_usd": round(cost_usd, 6),
            }
            tr = ToolResult(success=True, failure_mode=FailureMode.NONE, result=result_payload, latency_ms=latency)
            self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_end", latency=latency, job_id=job_id, extra={"tokens": total_tokens})
            return tr

        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_timeout", latency=latency, job_id=job_id)
            return ToolResult(success=False, failure_mode=FailureMode.TIMEOUT, latency_ms=latency, error_message="timeout")
        except Exception as exc:  # pragma: no cover - defensive
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "llm_tool", event_type="tool_error", latency=latency, job_id=job_id, extra={"error": str(exc)})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message=str(exc))
