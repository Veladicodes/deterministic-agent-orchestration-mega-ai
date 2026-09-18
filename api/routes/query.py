"""Non-streaming query execution endpoint.

Complements /query/stream (SSE) with a synchronous endpoint that returns
the complete PipelineResult in one response, including a deterministic
execution_hash computed the same way evaluation/replay.py does. This is
what the frontend's ReplayDiffView calls twice (e.g. the same query run
in stub mode) to obtain two hashes to compare.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from orchestration.pipeline import PipelineRunner
from evaluation.replay import ExecutionReplayer

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    query: str


def sanitize_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip purely-timing fields (latency_ms) before hashing/comparing.

    Two runs of the same query under the same (deterministic) backend
    configuration should produce the same *decisions and content* even
    though wall-clock latency inevitably differs run to run. Including
    latency_ms in the hash would make even a fully deterministic stub-mode
    run never match itself — that would make the replay/diff feature
    useless as a reproducibility check, so latency is intentionally
    excluded from the hashed/compared snapshot (it's still returned to
    the frontend separately, for display, from the raw execution_trace).
    """
    sanitized = []
    for call in tool_calls:
        sanitized.append(
            {
                "tool_name": call.get("tool_name"),
                "success": call.get("success"),
                "retries": call.get("retries"),
                "output": call.get("output"),
            }
        )
    return sanitized


def sanitize_routing_decisions(routing_decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip the wall-clock `timestamp` field before hashing/comparing.

    Routing decisions are deterministic given the same query and backend
    configuration (same heuristics, same order), but each decision is
    stamped with `datetime.utcnow().isoformat()` at record time
    (orchestration/pipeline.py's `_record_decision`), which necessarily
    differs between separate runs. Keeping the decision content
    (decision_type, selected_action, confidence, ...) while dropping the
    timestamp is what makes two equivalent runs hash identically.
    """
    sanitized = []
    for decision in routing_decisions:
        sanitized.append({k: v for k, v in decision.items() if k != "timestamp"})
    return sanitized


def build_state_transitions(summary: Dict[str, Any]) -> List[List[str]]:
    """Derive a small, deterministic state-transition list from the
    pipeline's summary (status, started_at, completed_at), serialized as
    [state, iso_timestamp] pairs so it round-trips through JSON.
    """
    started = summary.get("started_at")
    completed = summary.get("completed_at")
    status = summary.get("status", "unknown")
    transitions = []
    if started:
        transitions.append(["RUNNING", started])
    if completed:
        transitions.append([str(status).upper(), completed])
    return transitions


def compute_execution_hash(query: str, agent_sequence: List[str], tool_calls: List[Dict[str, Any]], routing_decisions: List[Dict[str, Any]]) -> str:
    replayer = ExecutionReplayer()
    return replayer.compute_trace_hash(
        {
            "query": query,
            "agent_sequence": agent_sequence,
            "tool_calls": sanitize_tool_calls(tool_calls),
            "state_transitions": [],
            "execution_path": {"routing_decisions": sanitize_routing_decisions(routing_decisions)},
        }
    )


@router.post("/query/run")
async def run_query(request: QueryRequest) -> dict:
    """Execute the full pipeline synchronously and return the result.

    Response includes `execution_hash`, computed from the query, the
    agents that ran, sanitized tool-call outcomes (content only, not
    latency), and routing decisions — so two runs of the same query
    under the same backend configuration produce the same hash iff they
    made the same decisions and got the same tool results, regardless of
    how long each run took.
    """
    runner = PipelineRunner()
    result = await runner.run(request.query)

    agent_sequence = [
        event.get("agent_id")
        for event in result.execution_trace.get("agent_events", [])
    ]
    routing_decisions = result.execution_trace.get("routing_decisions", [])
    tool_calls = result.execution_trace.get("tool_calls", [])

    execution_hash = compute_execution_hash(request.query, agent_sequence, tool_calls, routing_decisions)

    summary_dict = result.summary.model_dump(mode="json")
    execution_trace = dict(result.execution_trace)
    execution_trace["state_transitions"] = build_state_transitions(summary_dict)

    synthesizer_output = result.agent_outputs.get("synthesizer") or {}
    confidence_score = (synthesizer_output.get("metadata") or {}).get("confidence")

    return {
        "job_id": result.summary.job_id,
        "query": request.query,
        "success": result.success,
        "final_answer": result.final_answer,
        "confidence_score": confidence_score,
        "provenance_links": result.provenance_links,
        "execution_trace": execution_trace,
        "execution_hash": execution_hash,
        "summary": summary_dict,
        "errors": result.errors,
        "warnings": result.warnings,
    }
