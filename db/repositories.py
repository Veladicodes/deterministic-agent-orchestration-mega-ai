from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.persistence import AgentLog, Job, ToolCall
from db.persistence_logging import PersistenceLogger
from shared.enums import ExecutionStatus, FailureMode


persistence_logger = PersistenceLogger()


async def create_job(session: AsyncSession, original_query: str, status: ExecutionStatus = ExecutionStatus.PENDING) -> Job:
    """Create and persist a new job row.

    The helper is intentionally explicit so callers remain in control of
    transaction boundaries while still getting structured persistence logs.
    """

    job = Job(original_query=original_query, status=status)
    started = datetime.now(timezone.utc)
    try:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        persistence_logger.db_write_success(str(job.id), "job", latency_ms=latency_ms)
        return job
    except Exception as exc:
        await session.rollback()
        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        persistence_logger.db_write_failure(None, "job", str(exc), latency_ms=latency_ms)
        raise


async def write_agent_log(
    session: AsyncSession,
    job_id: UUID,
    agent_id: str,
    event_type: str,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    token_count: int = 0,
    latency_ms: float | None = None,
    policy_violations: list[str] | None = None,
) -> AgentLog:
    """Persist a structured agent log row."""

    record = AgentLog(
        job_id=job_id,
        agent_id=agent_id,
        event_type=event_type,
        input_payload=input_payload or {},
        output_payload=output_payload or {},
        token_count=token_count,
        latency_ms=latency_ms,
        policy_violations=policy_violations or [],
        timestamp=datetime.now(timezone.utc),
    )
    started = datetime.now(timezone.utc)
    try:
        session.add(record)
        await session.commit()
        await session.refresh(record)
        persistence_logger.db_write_success(str(job_id), "agent_log", latency_ms=(datetime.now(timezone.utc) - started).total_seconds() * 1000.0)
        return record
    except Exception as exc:
        await session.rollback()
        persistence_logger.db_write_failure(str(job_id), "agent_log", str(exc), latency_ms=(datetime.now(timezone.utc) - started).total_seconds() * 1000.0)
        raise


async def write_tool_call_log(
    session: AsyncSession,
    job_id: UUID,
    tool_name: str,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    retry_number: int = 0,
    latency_ms: float | None = None,
    accepted: bool = False,
    failure_mode: FailureMode = FailureMode.NONE,
) -> ToolCall:
    """Persist a structured tool call row."""

    record = ToolCall(
        job_id=job_id,
        tool_name=tool_name,
        input_payload=input_payload or {},
        output_payload=output_payload or {},
        retry_number=retry_number,
        latency_ms=latency_ms,
        accepted=accepted,
        failure_mode=failure_mode,
        timestamp=datetime.now(timezone.utc),
    )
    started = datetime.now(timezone.utc)
    try:
        session.add(record)
        await session.commit()
        await session.refresh(record)
        persistence_logger.db_write_success(str(job_id), "tool_call", latency_ms=(datetime.now(timezone.utc) - started).total_seconds() * 1000.0)
        return record
    except Exception as exc:
        await session.rollback()
        persistence_logger.db_write_failure(str(job_id), "tool_call", str(exc), latency_ms=(datetime.now(timezone.utc) - started).total_seconds() * 1000.0)
        raise


async def get_execution_trace(session: AsyncSession, job_id: UUID) -> dict[str, Any]:
    """Retrieve a job and its trace artifacts for debugging/reproducibility."""

    job_result = await session.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        persistence_logger.trace_created(str(job_id), "execution_trace", 0)
        return {"job": None, "agent_logs": [], "tool_calls": []}

    agent_logs_result = await session.execute(select(AgentLog).where(AgentLog.job_id == job_id).order_by(AgentLog.timestamp.asc()))
    tool_calls_result = await session.execute(select(ToolCall).where(ToolCall.job_id == job_id).order_by(ToolCall.timestamp.asc()))

    agent_logs = agent_logs_result.scalars().all()
    tool_calls = tool_calls_result.scalars().all()

    trace = {
        "job": job,
        "agent_logs": agent_logs,
        "tool_calls": tool_calls,
    }
    persistence_logger.trace_created(str(job_id), "execution_trace", len(agent_logs) + len(tool_calls))
    return trace
