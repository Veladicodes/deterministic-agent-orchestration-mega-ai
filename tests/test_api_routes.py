"""Tests for the non-streaming query and replay-compare API routes.

Calls route handlers directly (same pattern as tests/test_health.py) so
these tests don't require a running DB/Redis-backed FastAPI app.
"""

from __future__ import annotations

import asyncio

import api.routes.query as query_module
import api.routes.replay as replay_module


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_run_query_returns_execution_hash_and_success():
    request = query_module.QueryRequest(query="What is deterministic orchestration?")
    result = run_async(query_module.run_query(request))

    assert result["success"] is True
    assert isinstance(result["execution_hash"], str)
    assert len(result["execution_hash"]) == 64  # sha256 hex digest
    assert result["query"] == "What is deterministic orchestration?"
    assert "execution_trace" in result


def test_identical_queries_produce_identical_hashes_in_stub_mode():
    request = query_module.QueryRequest(query="What is machine learning?")
    result_a = run_async(query_module.run_query(request))
    result_b = run_async(query_module.run_query(request))

    assert result_a["execution_hash"] == result_b["execution_hash"]


def test_compare_traces_reports_identical_for_matching_runs():
    request = query_module.QueryRequest(query="What is machine learning?")
    result_a = run_async(query_module.run_query(request))
    result_b = run_async(query_module.run_query(request))

    compare_request = replay_module.CompareRequest(
        trace_a=replay_module.TraceInput(
            job_id=result_a["job_id"], query=result_a["query"], execution_trace=result_a["execution_trace"]
        ),
        trace_b=replay_module.TraceInput(
            job_id=result_b["job_id"], query=result_b["query"], execution_trace=result_b["execution_trace"]
        ),
    )
    comparison = run_async(replay_module.compare_traces(compare_request))

    assert comparison["identical"] is True
    assert comparison["trace_a_valid"] is True
    assert comparison["trace_b_valid"] is True


def test_compare_traces_reports_divergence_for_different_queries():
    request_a = query_module.QueryRequest(query="What is machine learning?")
    request_b = query_module.QueryRequest(query="Compare PostgreSQL and Redis")
    result_a = run_async(query_module.run_query(request_a))
    result_b = run_async(query_module.run_query(request_b))

    compare_request = replay_module.CompareRequest(
        trace_a=replay_module.TraceInput(
            job_id=result_a["job_id"], query=result_a["query"], execution_trace=result_a["execution_trace"]
        ),
        trace_b=replay_module.TraceInput(
            job_id=result_b["job_id"], query=result_b["query"], execution_trace=result_b["execution_trace"]
        ),
    )
    comparison = run_async(replay_module.compare_traces(compare_request))

    assert comparison["identical"] is False
    assert comparison["divergence_count"] > 0
