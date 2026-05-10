# Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MULTI-AGENT ORCHESTRATION SYSTEM                │
└─────────────────────────────────────────────────────────────────────────┘

                            USER QUERY
                                 │
                                 ▼
                         ┌──────────────┐
                         │  API GATEWAY │
                         │ (FastAPI)    │
                         └──────────────┘
                                 │
                                 ▼
                         ┌──────────────────────┐
                         │  PIPELINE RUNNER     │
                         │ (Orchestration)      │
                         └──────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │ EXECUTION   │    │  RETRY      │    │  RESULT     │
    │ STATE MGR   │    │ COORDINATOR │    │  ASSEMBLER  │
    └─────────────┘    └─────────────┘    └─────────────┘
         │
         │  Coordinates Agent Sequence
         │
    ┌────┴────┬─────────┬──────────┬──────────┐
    │          │         │          │          │
    ▼          ▼         ▼          ▼          ▼
┌─────────┐┌─────────┐┌──────────┐┌────────┐┌──────────┐
│DECOMPOSE││RETRIEVE ││ CRITIQUE ││SYNTHESIZE         │
│ AGENT   ││ AGENT   ││ AGENT    ││ AGENT  │          │
└────┬────┘└────┬────┘└────┬─────┘└───┬────┘          │
     │          │          │         │                │
     └──────────┴──────────┴─────────┘                │
            DETERMINISTIC AGENT PIPELINE             │
                    │                                 │
                    ▼                                 │
            ┌──────────────┐                          │
            │  PERSISTENCE │◄─────────────────────────┘
            │  (SQLAlchemy)│
            └──────────────┘
                    │
                    ├──► EXECUTION_RUNS
                    ├──► METRICS
                    ├──► FAILURES
                    └──► TRACES

```

## Agent Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DETERMINISTIC EXECUTION                          │
└─────────────────────────────────────────────────────────────────────────┘

INPUT: User Query
  "Compare PostgreSQL and Redis for caching"
  │
  ▼
[1] DECOMPOSER AGENT
  ├─ Parse query structure
  ├─ Identify sub-tasks
  ├─ Check for ambiguity
  └─ Output: DecomposedQuery
       {
         "main_tasks": ["retrieve_postgresql_properties", "retrieve_redis_properties"],
         "comparison_points": ["performance", "consistency", "operability"],
         "ambiguity_flags": []
       }
  │
  ▼
[2] RETRIEVER AGENT
  ├─ Tool call: WebSearchTool("PostgreSQL performance characteristics")
  ├─ Tool call: WebSearchTool("Redis caching best practices")
  ├─ Retry on timeout (exponential backoff: 100ms, 200ms, 400ms)
  └─ Output: RetrievalResults
       {
         "results": [
           {"query": "...", "source": "...", "confidence": 0.85},
           {"query": "...", "source": "...", "confidence": 0.72}
         ]
       }
  │
  ▼
[3] CRITIC AGENT
  ├─ Check for contradictions (boolean conflicts)
  ├─ Assess provenance coverage
  ├─ Flag low-confidence claims
  └─ Output: CriticAnalysis
       {
         "contradictions": [],
         "provenance_coverage": 0.78,
         "low_confidence_claims": ["claim_id_7"],
         "confidence_score": 0.82
       }
  │
  ▼
[4] SYNTHESIZER AGENT
  ├─ Assemble final answer with provenance
  ├─ Remove low-confidence claims
  ├─ Include comparison points
  └─ Output: StructuredAnswer
       {
         "answer_text": "...",
         "provenance": [
           {"claim": "...", "source": "...", "confidence": 0.85}
         ],
         "confidence": 0.82,
         "caveats": []
       }
  │
  ▼
OUTPUT: Final Result
  {
    "status": "success",
    "answer": {...},
    "execution_trace": {...},
    "metrics": {...}
  }

```

## Evaluation and Replay Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      EVALUATION & REPLAYABILITY                         │
└─────────────────────────────────────────────────────────────────────────┘

EVALUATION RUN
     │
     ├─→ Load: 40 curated queries (5 categories)
     │
     ├─→ Execute: PipelineRunner for each query
     │
     ├─→ Collect:
     │   ├─ Execution trace (agent sequence, tool calls, state transitions)
     │   ├─ Metrics (latency, retries, completion rate)
     │   └─ Failures (classification, recovery rate)
     │
     ├─→ Persist:
     │   ├─ evaluation_runs
     │   ├─ metrics_snapshots
     │   ├─ failure_logs
     │   └─ execution_traces
     │
     └─→ Report:
         ├─ JSON summary
         ├─ Markdown report
         ├─ Failure analysis
         └─ Weak areas report

REPLAY SINGLE EXECUTION
     │
     ├─→ Load: Stored execution trace (immutable)
     │
     ├─→ Validate: Trace integrity
     │   ├─ Agent sequence present?
     │   ├─ Tool calls recorded?
     │   └─ State transitions valid?
     │
     ├─→ Compare: Against original execution
     │   ├─ Same agent sequence?
     │   ├─ Same tool responses?
     │   └─ Same final result?
     │
     └─→ Debug: Identify divergence or validate fix

METRICS AGGREGATION
     │
     ├─→ Latency Analysis
     │   ├─ Per-agent (decomposer, retriever, critic, synthesizer)
     │   ├─ Percentiles (p50, p95, p99)
     │   └─ Retry overhead
     │
     ├─→ Failure Analysis
     │   ├─ By type (retrieval, provenance, contradiction, etc.)
     │   ├─ By agent (where did failure occur?)
     │   └─ Recovery rate
     │
     ├─→ Quality Metrics
     │   ├─ Completion rate
     │   ├─ Provenance coverage
     │   ├─ Confidence score
     │   └─ Category success rates
     │
     └─→ Reports
         ├─ Summary statistics
         ├─ Category breakdown
         ├─ Trend analysis
         └─ Weak areas identification

```

## Persistence Layer

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PERSISTENCE & OBSERVABILITY                        │
└─────────────────────────────────────────────────────────────────────────┘

PostgreSQL Database
├─ execution_runs
│  ├─ id (UUID)
│  ├─ query
│  ├─ status
│  ├─ started_at
│  └─ completed_at
│
├─ metrics
│  ├─ job_id
│  ├─ total_latency_ms
│  ├─ decomposer_latency_ms
│  ├─ retriever_latency_ms
│  ├─ critic_latency_ms
│  ├─ synthesizer_latency_ms
│  ├─ retry_count
│  └─ [10 more fields: confidence, provenance, etc.]
│
├─ failures
│  ├─ failure_id
│  ├─ job_id
│  ├─ failure_type (enum: retrieval, provenance, contradiction, etc.)
│  ├─ agent_id
│  ├─ error_message
│  └─ timestamp
│
├─ traces
│  ├─ trace_id
│  ├─ original_job_id
│  ├─ agent_sequence (JSON array)
│  ├─ tool_calls (JSON array)
│  ├─ state_transitions (JSON array)
│  └─ execution_path (JSON)
│
└─ evaluation_runs
   ├─ evaluation_run_id
   ├─ dataset_id
   ├─ query_count
   ├─ succeeded_queries
   ├─ failed_queries
   └─ [aggregated metrics]

```

## Data Flow Summary

```
                           USER INPUT

                              │
                              ▼
                        ┌─────────────┐
                        │  API LAYER  │
                        └─────────────┘
                              │
                              ▼
                    ┌──────────────────────┐
                    │  PIPELINE RUNNER     │
                    │ (Deterministic)      │
                    └──────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
            ┌─────────────┐      ┌──────────────┐
            │   AGENTS    │      │  PERSISTENCE │
            │ (Sequential)│      │  (Async ORM) │
            └─────────────┘      └──────────────┘
                    │                   │
                    └─────────┬─────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │   DATABASE   │
                        │ (PostgreSQL) │
                        └──────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
                    ▼                    ▼
            ┌──────────────┐      ┌──────────────┐
            │   METRICS    │      │  TRACES &    │
            │   & RESULTS  │      │  FAILURE     │
            │              │      │  ANALYSIS    │
            └──────────────┘      └──────────────┘
                    │                    │
                    └─────────┬──────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │  EVALUATION  │
                        │  FRAMEWORK   │
                        │  (Reports)   │
                        └──────────────┘

```

## Key Design Principles

1. **Deterministic Pipeline**: No branching, no dynamic decisions. Same input → identical execution path
2. **Observable**: Every operation logged with structured records
3. **Traceable**: Immutable execution traces enable replay and debugging
4. **Testable**: All components tested with deterministic behavior verification
5. **Persistent**: Full execution history available for analysis
6. **Fault-Tolerant**: RetryCoordinator handles transient failures automatically

---

For detailed information, see [ARCHITECTURE.md](../ARCHITECTURE.md)
