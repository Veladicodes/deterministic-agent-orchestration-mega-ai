from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from db.base import Base
from db.models import AgentLog, EvalRun, Job, PromptRewrite, ToolCall
from db.repositories import create_job, get_execution_trace, write_agent_log, write_tool_call_log
from shared.enums import ExecutionStatus, FailureMode, ReviewStatus


@pytest.fixture()
def sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
    )
    return engine


def test_model_creation_defaults():
    job = Job(original_query="example query")
    agent_log = AgentLog(
        job_id=job.id,
        agent_id="agent-a",
        event_type="started",
        input_payload={},
        output_payload={},
        token_count=0,
        policy_violations=[],
    )
    tool_call = ToolCall(
        job_id=job.id,
        tool_name="web_search",
        input_payload={},
        output_payload={},
        retry_number=0,
        accepted=False,
        failure_mode=FailureMode.NONE,
    )
    eval_run = EvalRun(category="smoke", summary_scores={}, justifications={})
    prompt_rewrite = PromptRewrite(
        agent_id="agent-a",
        original_prompt="orig",
        proposed_prompt="new",
        diff="diff",
        justification="reason",
    )

    assert job.status == ExecutionStatus.PENDING
    assert agent_log.event_type == "started"
    assert tool_call.failure_mode == FailureMode.NONE
    assert eval_run.category == "smoke"
    assert prompt_rewrite.status == ReviewStatus.PENDING


def test_repository_writes_and_trace_retrieval(sqlite_engine):
    async def _run():
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
        async with session_factory() as session:
            job = await create_job(session, original_query="why is the system down?")
            assert job.id is not None

            agent_log = await write_agent_log(
                session,
                job_id=job.id,
                agent_id="agent-1",
                event_type="analysis_started",
                input_payload={"step": 1},
                output_payload={"status": "ok"},
                token_count=12,
                latency_ms=3.5,
                policy_violations=["none"],
            )
            assert agent_log.job_id == job.id
            assert agent_log.token_count == 12

            tool_call = await write_tool_call_log(
                session,
                job_id=job.id,
                tool_name="web_search",
                input_payload={"query": "status"},
                output_payload={"results": []},
                retry_number=0,
                latency_ms=1.25,
                accepted=True,
            )
            assert tool_call.accepted is True

            trace = await get_execution_trace(session, job.id)
            assert trace["job"].id == job.id
            assert len(trace["agent_logs"]) == 1
            assert len(trace["tool_calls"]) == 1

    asyncio.run(_run())


def test_trace_retrieval_missing_job(sqlite_engine):
    async def _run():
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
        async with session_factory() as session:
            missing_trace = await get_execution_trace(session, job_id=Job(original_query="x").id)
            assert missing_trace["job"] is None
            assert missing_trace["agent_logs"] == []
            assert missing_trace["tool_calls"] == []

    asyncio.run(_run())
