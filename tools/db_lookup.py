from __future__ import annotations

import re
import time
from typing import Dict, Any

from sqlalchemy import text

from db.session import engine
from shared.exec_logger import ExecutionLogger
from shared.tool_base import BaseTool, ToolResult
from shared.enums import FailureMode


_SELECT_RE = re.compile(r"^\s*select\s+.+", re.IGNORECASE | re.DOTALL)


class DatabaseLookupTool(BaseTool):
    """Execute validated read-only SQL queries against the configured DB.

    Safety notes:
    - Only simple SELECT queries are allowed by default (no semicolons,
      no DML statements). This is a conservative validation to avoid
      accidental data mutations from higher-level components.
    - Malformed or disallowed queries return `FailureMode.MALFORMED`.
    - The tool executes asynchronously using the shared SQLAlchemy async engine.
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.exec_logger = ExecutionLogger()

    def _validate_query(self, sql: str) -> bool:
        # Reject multiple statements
        if ";" in sql.strip().rstrip(";"):
            return False
        # Only allow queries that look like SELECT ...
        return bool(_SELECT_RE.match(sql))

    async def run(self, payload: Dict[str, Any], timeout_seconds: float | None = None) -> ToolResult:
        sql = (payload or {}).get("sql")
        start = time.perf_counter()
        self.exec_logger.log_event(agent_id=self.name or "dblookup", event_type="tool_start", job_id=payload.get("job_id") if payload else None)

        if not sql or not isinstance(sql, str):
            latency = (time.perf_counter() - start) * 1000.0
            return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="missing sql")

        if not self._validate_query(sql):
            latency = (time.perf_counter() - start) * 1000.0
            return ToolResult(success=False, failure_mode=FailureMode.MALFORMED, latency_ms=latency, error_message="only single SELECT queries allowed")

        try:
            # Execute the query using the shared engine. We don't enforce a timeout
            # at the DB driver level here; callers should wrap calls with cancelation
            # if they require strict time bounds.
            async with engine.connect() as conn:
                result = await conn.execute(text(sql))
                rows = [dict(r) for r in result.mappings().all()]

            latency = (time.perf_counter() - start) * 1000.0
            out = {"rows": rows, "row_count": len(rows)}
            self.exec_logger.log_event(agent_id=self.name or "dblookup", event_type="tool_end", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"row_count": len(rows)})
            return ToolResult(success=True, failure_mode=FailureMode.NONE, latency_ms=latency, result=out)
        except Exception as exc:  # pragma: no cover - runtime DB errors
            latency = (time.perf_counter() - start) * 1000.0
            self.exec_logger.log_event(agent_id=self.name or "dblookup", event_type="tool_error", latency=latency, job_id=payload.get("job_id") if payload else None, extra={"error": str(exc)})
            return ToolResult(success=False, failure_mode=FailureMode.INTERNAL, latency_ms=latency, error_message=str(exc))
