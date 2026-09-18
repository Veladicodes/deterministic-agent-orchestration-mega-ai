# SSE Event Vocabulary

`POST /api/v1/query/stream` streams newline-delimited SSE events (`data: <json>\n\n`) as the pipeline executes, via `orchestration/pipeline.py`'s `PipelineRunner._emit()` callback. Every event is a flat JSON object with an `event_type` key plus type-specific fields.

| `event_type` | Emitted by | Fields | Meaning |
|---|---|---|---|
| `stream_started` | `api/routes/stream.py` | `query` | The stream has opened; the pipeline is about to start. |
| `orchestration_update` | `pipeline.py` | `job_id`, `state`, `query` | Pipeline-level lifecycle marker (currently only `state: "started"`). |
| `agent_started` | `pipeline.py` | `agent_id` | A pipeline stage (`decomposer`\|`retriever`\|`critic`\|`synthesizer`) is about to run. Not emitted for a stage the router skips entirely. |
| `agent_completed` | `pipeline.py` | `agent_id` | The stage named in the matching `agent_started` has finished (success or failure — check the final result for outcome). |
| `routing_decision` | `pipeline.py` | `decision_type`, `selected_action`, `trigger_reason` | A deterministic routing choice (e.g. `skip_retriever`, `invoke_critic`, `compress_context`). This is the direct evidence of the "deterministic orchestration" thesis — same query, same routing decisions, every run. |
| `adversarial_detected` | `pipeline.py` | `indicators` | The query matched one of the adversarial-input heuristics. |
| `tool_call_completed` | `pipeline.py` | `tool`, `success` | A non-agent tool call finished (currently only the self-reflection fallback tool). |
| `pipeline_error` | `api/routes/stream.py` | `error` | An unhandled exception aborted the run. |
| `stream_complete` | `api/routes/stream.py` | — | Terminal event; the SSE connection closes after this. |

## Frontend usage

`frontend/src/components/PipelineTimeline.tsx` renders `agent_started`/`agent_completed`/`routing_decision` events live as they arrive, and reconciles them against the final `/query/run` result's `execution_trace.agent_events` (which carries per-stage latency/retries/tokens — not available at SSE time) once the run finishes.

## Extending this vocabulary

New event types should follow the existing shape (`event_type` + a small number of flat fields) and be added to this table. `PipelineRunner._emit()` is a no-op unless a caller passes an `event_sink`, so new call sites are safe to add without affecting non-streaming callers (`/query/run`, `scripts/run_evaluation.py`).
