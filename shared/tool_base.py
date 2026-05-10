from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from shared.enums import FailureMode


class ToolResult(BaseModel):
    """Typed tool result returned by tool implementations.

    - `success`: True if the tool produced an acceptable result.
    - `failure_mode`: one of the declared `FailureMode` values when not successful.
    - `result`: optional structured payload (tool-specific).
    - `latency_ms`: measured execution time in milliseconds.
    - `retry_count`: number of retries attempted.
    - `accepted`: boolean indicating whether the calling agent accepted it.
    - `rejected`: boolean indicating whether it was rejected by policy or parsing.
    - `error_message`: optional human-friendly error.
    """

    success: bool = False
    failure_mode: FailureMode = FailureMode.NONE
    result: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None
    retry_count: int = 0
    accepted: bool = False
    rejected: bool = False
    error_message: Optional[str] = None


@dataclass
class RetryPolicy:
    max_retries: int = 0
    backoff_seconds: float = 0.0


class BaseTool(ABC):
    """Minimal abstract tool interface.

    Tools should implement `run()` and return a `ToolResult`. The base
    provides a tiny helper for timing execution and tracking retries.
    """

    name: str

    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__

    @abstractmethod
    async def run(self, payload: Dict[str, Any], timeout_seconds: Optional[float] = None) -> ToolResult:
        """Execute the tool. Implementations must return a ToolResult.

        Keep implementations framework-agnostic — do not perform orchestration
        here. Timeouts should be enforced by the caller or the runtime.
        """
        raise NotImplementedError()

    async def execute_with_retry(self, payload: Dict[str, Any], retry: RetryPolicy) -> ToolResult:
        """Simple retry helper that measures latency and collects retry metadata.

        This helper does not implement sophisticated backoffs or jitter — the
        policy is intentionally minimal and synchronous so orchestration can
        call it in an async context and decide how to schedule retries.
        """
        attempt = 0
        last_result: Optional[ToolResult] = None
        while True:
            attempt += 1
            start = time.perf_counter()
            try:
                last_result = await self.run(payload)
            except Exception as exc:  # pragma: no cover - tool implementers handle specifics
                end = time.perf_counter()
                last_result = ToolResult(
                    success=False,
                    failure_mode=FailureMode.INTERNAL,
                    error_message=str(exc),
                    latency_ms=(end - start) * 1000.0,
                    retry_count=attempt - 1,
                )

            # attach retry metadata
            last_result.retry_count = attempt - 1
            if last_result.latency_ms is None:
                # best-effort set from measured time
                end = time.perf_counter()
                last_result.latency_ms = (end - start) * 1000.0

            if last_result.success or attempt > retry.max_retries:
                return last_result

            # small synchronous sleep; orchestration may prefer async backoff
            if retry.backoff_seconds:
                import time as _time

                _time.sleep(retry.backoff_seconds)
