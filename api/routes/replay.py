"""Replay/diff endpoint backing the frontend's ReplayDiffView.

Wraps evaluation/replay.py's ExecutionReplayer so the browser can compare
two execution traces (e.g. two runs of the same query) without needing
its own reimplementation of the hashing/comparison logic — the frontend
sends back exactly what /query/run gave it for each run.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from evaluation.replay import ExecutionReplayer
from api.routes.query import sanitize_tool_calls, sanitize_routing_decisions

router = APIRouter(tags=["replay"])


class TraceInput(BaseModel):
    job_id: str
    query: str
    execution_trace: Dict[str, Any]


class CompareRequest(BaseModel):
    trace_a: TraceInput
    trace_b: TraceInput


def _agent_sequence(execution_trace: Dict[str, Any]) -> List[str]:
    return [event.get("agent_id") for event in execution_trace.get("agent_events", [])]


def _synthetic_state_transitions(execution_trace: Dict[str, Any]) -> List[tuple[str, datetime]]:
    """Extract just the state *names* from /query/run's
    execution_trace["state_transitions"] and pair them with synthetic,
    deterministic timestamps.

    Real wall-clock timestamps are dropped intentionally: two separate
    runs of the same query happen at different real times by definition,
    so including real timestamps in the hashed snapshot would make
    `compare_traces` report every pair of runs as divergent even when
    they made identical decisions — which would make this endpoint
    useless as a "did this replay reproduce the same behavior?" check.
    `validate_trace` only requires a non-empty, well-formed list; it does
    not check timestamp values, so this synthetic list still satisfies it.
    """
    synthetic = []
    for index, entry in enumerate(execution_trace.get("state_transitions", [])):
        if len(entry) != 2:
            continue
        state, _ts = entry
        synthetic.append((state, datetime(2000, 1, 1) + timedelta(seconds=index)))
    return synthetic


def _build_trace(replayer: ExecutionReplayer, trace_input: TraceInput):
    return replayer.create_trace(
        original_job_id=trace_input.job_id,
        query=trace_input.query,
        agent_sequence=_agent_sequence(trace_input.execution_trace),
        tool_calls=sanitize_tool_calls(trace_input.execution_trace.get("tool_calls", [])),
        state_transitions=_synthetic_state_transitions(trace_input.execution_trace),
        execution_path={"routing_decisions": sanitize_routing_decisions(trace_input.execution_trace.get("routing_decisions", []))},
    )


@router.post("/replay/compare")
async def compare_traces(request: CompareRequest) -> dict:
    """Compare two execution traces (as returned by /query/run) and
    report divergences, using the same sanitized (latency-excluded)
    snapshot /query/run hashes with, so hashes agree for equivalent runs.
    """
    replayer = ExecutionReplayer()

    trace_a = _build_trace(replayer, request.trace_a)
    trace_b = _build_trace(replayer, request.trace_b)

    comparison = replayer.compare_traces(trace_a, trace_b)
    comparison["trace_a_valid"] = replayer.validate_trace(trace_a)
    comparison["trace_b_valid"] = replayer.validate_trace(trace_b)
    return comparison
