from __future__ import annotations

from typing import Any

from shared.exec_logger import ExecutionLogger


class PersistenceLogger:
    """Structured logger for persistence events.

    This remains intentionally thin: it only emits typed JSON events for
    DB writes, trace creation, and migration milestones.
    """

    def __init__(self) -> None:
        self._logger = ExecutionLogger(service_name="persistence")

    def db_write_success(self, job_id: str | None, entity: str, latency_ms: float | None = None) -> None:
        self._logger.log_event(
            agent_id="persistence",
            event_type="db_write_success",
            job_id=job_id,
            latency=latency_ms,
            extra={"entity": entity},
        )

    def db_write_failure(self, job_id: str | None, entity: str, error: str, latency_ms: float | None = None) -> None:
        self._logger.log_event(
            agent_id="persistence",
            event_type="db_write_failure",
            job_id=job_id,
            latency=latency_ms,
            policy_violation=error,
            extra={"entity": entity},
        )

    def trace_created(self, job_id: str | None, trace_type: str, count: int) -> None:
        self._logger.log_event(
            agent_id="persistence",
            event_type="trace_created",
            job_id=job_id,
            extra={"trace_type": trace_type, "count": count},
        )

    def migration_event(self, event_type: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.log_event(
            agent_id="persistence",
            event_type=event_type,
            extra=extra,
        )
