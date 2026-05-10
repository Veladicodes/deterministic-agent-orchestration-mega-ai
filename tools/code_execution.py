from __future__ import annotations

import asyncio
import sys
import time
from typing import Dict, Any

from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode


class CodeExecutionTool(BaseTool):
    """Safely execute isolated Python snippets in a subprocess.

    Design and safety notes:
    - Runs the snippet in a subprocess using the running Python interpreter
      (`sys.executable`) to avoid executing code in the host process.
    - Enforces a strict timeout via `asyncio.wait_for` and kills the child
      process on timeout to avoid hanging processes.
    - Captures `stdout`, `stderr`, and `exit_code` to return a structured
      result. No filesystem or network sandboxing is provided here; this
      is intended for controlled development use, not untrusted code.
    - For production, run code in a hardened sandbox (containers, seccomp,
      resource limits). This implementation focuses on deterministic
      behavior and observability for the assessment.
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.exec_logger = ExecutionLogger()

    async def run(self, payload: Dict[str, Any], timeout_seconds: float | None = None) -> ToolResult:
        code = (payload or {}).get("code")
        start = time.perf_counter()
        self.exec_logger.log_event(agent_id=self.name or "codeexec", event_type="tool_start", job_id=payload.get("job_id") if payload else None)

        if not code or not isinstance(code, str):
            latency = (time.perf_counter() - start) * 1000.0
            return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="no code provided")

        # Build subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            if timeout_seconds is not None:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout_seconds)
            else:
                stdout, stderr = await proc.communicate()
            exit_code = proc.returncode
            latency = (time.perf_counter() - start) * 1000.0

            result = {
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "exit_code": exit_code,
            }
            self.exec_logger.log_event(agent_id=self.name or "codeexec", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"exit_code": exit_code})
            return ToolResult(success=True, failure_mode=FailureMode.NONE, latency_ms=latency, result=result)

        except asyncio.TimeoutError:
            # Best-effort kill the child process
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "codeexec", event_type="tool_timeout", latency=latency, job_id=payload.get("job_id") if payload else None)
            return ToolResult(success=False, failure_mode=FailureMode.TIMEOUT, latency_ms=latency, error_message="execution timed out")
        except Exception as exc:  # pragma: no cover - defensive
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "codeexec", event_type="tool_error", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"error": str(exc)})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message=str(exc))
