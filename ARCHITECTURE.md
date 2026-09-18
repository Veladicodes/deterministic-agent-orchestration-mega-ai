# Architecture Overview

## System Design

This is a **deterministic, observable multi-agent orchestration system** designed for reproducible LLM query processing without autonomous loops or external frameworks.

### Core Principle

**Deterministic Sequential Execution**: Agents execute in a fixed sequence (Decomposer → Retriever → Critic → Synthesizer) with no dynamic branching, conditional skipping, or agent-initiated decisions. All outcomes are deterministic—same input produces identical execution trace and output.

## Execution Flow

```
User Query
    ↓
PipelineRunner (main orchestrator)
    ↓
1. DecomposerAgent: Parse query → detect intent, entities, ambiguities → generate sub-tasks
    ↓
2. RetrieverAgent: Execute 2-hop web search for each sub-task → collect provenance
    ↓
3. CriticAgent: Detect contradictions, assess confidence, flag suspicious claims
    ↓
4. SynthesizerAgent: Combine outputs, filter flagged claims, synthesize final answer
    ↓
PipelineResult (success/partial_failure/failed, final answer, provenance, traceability)
```

## Architecture Layers

### 1. **Shared Infrastructure** (`shared/`)

- **`settings.py`**: Configuration (DB URL, Redis URL, log level)
- **`enums.py`**: Execution states (PENDING, RUNNING, SUCCEEDED, PARTIAL_FAILURE, FAILED, CANCELLED)
- **`logging.py`**: Structured JSON logging with `get_logger()`
- **`exec_logger.py`**: ExecutionLogger for telemetry events (agent_id, event_type, latency, tokens)
- **`budget.py`**: Token/call budgets per agent (enforcement via BudgetManager)
- **`agent_base.py`**: AgentConfig, BaseAgent abstract class
- **`tool_base.py`**: ToolResult contract

### 2. **Tools Layer** (`tools/`)

- **`web_search.py`**: WebSearchTool - 2-hop retrieval with retry
- **`code_execution.py`**: CodeExecutionTool - deterministic code execution (no LLM calls)
- **`database_lookup.py`**: DatabaseLookupTool - PostgreSQL queries
- **`self_reflection.py`**: SelfReflectionTool - deterministic analysis

### 3. **Shared Context** (`context/`)

- **`shared_context.py`**: 
  - `SharedContext`: Job-wide mutable context (sub_tasks, agent_outputs, tool_calls, provenance)
  - `ExecutionState`: Status tracking (PENDING → RUNNING → terminal state)
  - `AgentOutput`: Agent results (output_text, tokens_used, tool_calls, metadata)
  - `ProvenanceRecord`: Source tracking (tool_id, step, result)

### 4. **Agent Layer** (`agents/`)

Deterministic agents with no LLM calls. Each agent:
- Reads from SharedContext
- Executes deterministic rules (regex, heuristics, string matching)
- Writes to SharedContext.agent_outputs
- Produces typed output (DecomposerOutput, RetrieverOutput, CritiqueOutput, SynthesisOutput)

#### DecomposerAgent
- Input: original query
- Process: Regex-based intent/entity detection, ambiguity flagging, dependency graph building
- Output: Sub-tasks, dependencies, ambiguity flags

#### RetrieverAgent  
- Input: Sub-tasks from Decomposer
- Process: WebSearchTool (2-hop search per sub-task, refinement between hops)
- Output: Search results with provenance records

#### CriticAgent
- Input: Decomposer, Retriever outputs
- Process: Contradiction detection (keyword matching), confidence scoring (based on source depth/diversity)
- Output: Flagged claims, overall confidence

#### SynthesizerAgent
- Input: All prior agent outputs
- Process: Build claim pool, filter flagged claims, synthesize via string interpolation
- Output: Final answer, provenance links, removed claims, confidence

### 5. **Orchestration Layer** (`orchestration/`)

Deterministic, observable coordination of agents.

#### ExecutionStateManager
- State machine: PENDING → RUNNING → (SUCCEEDED | PARTIAL_FAILURE | FAILED | CANCELLED)
- Tracks transitions with timestamps for debugging

#### RetryCoordinator
- Exponential backoff: backoff_ms = min(max_backoff, initial * multiplier^attempt)
- Max retries: 3, initial backoff: 100ms, multiplier: 2.0, max: 30000ms
- Returns: (success, result, retry_records)

#### ResultAssembler
- Collects agent execution events (latency, tokens, retries)
- Accumulates errors/warnings
- Assembles final PipelineResult with metrics

#### PipelineRunner
- Executes agents in fixed sequence
- Failure handling:
  - Decomposer failure: block (FAILED)
  - Retriever/Critic failure: partial_failure but continue
  - Synthesizer failure: block (FAILED)
- Returns: PipelineResult (success, final_answer, agent_outputs, execution_trace, provenance_links)

### 6. **Persistence Layer** (`db/`)

- **Models**: ExecutionTrace, ToolCall (SQLAlchemy ORM)
- **Repositories**: ExecutionTraceRepository (write traces, retrieve by job_id)
- **Migrations**: Alembic (bootstrap DDL, schema changes)

## State Transitions

```
PENDING
  ↓ (initialize)
RUNNING
  ├─ (partial agent failure) → PARTIAL_FAILURE
  │  ├─ (continue, then block on Synthesizer) → FAILED
  │  └─ (continue to success) → SUCCEEDED
  ├─ (block failure) → FAILED
  ├─ (explicit cancel) → CANCELLED
  └─ (all complete) → SUCCEEDED
```

## Observability & Traceability

### Logging
- **Structured JSON**: ExecutionLogger emits {ts, service, agent_id, event_type, latency_ms, token_count, job_id}
- **Per-agent logs**: DecomposerAgent, RetrieverAgent, CriticAgent, SynthesizerAgent log start/completion
- **State transitions**: Tracked with timestamps

### Execution Trace
- Job ID (UUID)
- Sub-tasks (from Decomposer)
- Tool calls (aggregated)
- Agent outputs (all 4 agents)
- Provenance links (source → claim chain)

### Determinism Guarantees
- Fixed agent sequence (no branching)
- Deterministic regex patterns (same input → same decomposition)
- Web search results are deterministic per tool (external, but called consistently)
- No randomness in synthesis (string formatting only)

## Failure Modes & Recovery

| Failure | Recovery | State |
|---------|----------|-------|
| Decomposer fails | Block | FAILED |
| Retriever fails | Skip, warn, continue | PARTIAL_FAILURE |
| Critic fails | Skip, warn, continue | PARTIAL_FAILURE |
| Synthesizer fails | Block | FAILED |
| Retry exhaustion | Mark failure, stop | FAILED |

## Why This Architecture?

1. **No LLMs**: All agents are deterministic rule engines (no hallucination risk)
2. **No Autonomous Loops**: Fixed sequence only
3. **No External Frameworks**: Pure async/await, Pydantic, SQLAlchemy, no LangChain/AutoGen/CrewAI
4. **Observable**: Full traceability from query to final answer
5. **Reproducible**: Same input → identical execution, token counts, provenance
6. **Testable**: No random behavior, no external dependencies (tools mocked in tests)

## Tradeoffs

| Decision | Benefit | Cost |
|----------|---------|------|
| Fixed agent sequence | Predictable, traceable | No flexibility, no branching |
| Deterministic rules | Reproducible, debuggable | Limited expressiveness vs. LLM reasoning |
| Regex-based parsing | Fast, observable | Pattern maintenance, edge cases |
| 2-hop retrieval | Balanced coverage, traceable | May miss deep context |
| Keyword contradiction detection | Deterministic, fast | False positives/negatives |

## Pluggable Backends and the Determinism Boundary

Real backends exist for two of the four agents (`tools/real_web_search_tool.py` for the Retriever, `agents/llm_synthesizer.py` / `tools/llm_tool.py` for the Synthesizer — see README's "Real Backends" section). Both are opt-in via `Settings.use_real_backends` and are selected in `orchestration/pipeline.py`'s `_build_web_search_tool()` / `_build_synthesizer_agent()`; the deterministic stub path remains the default with no configuration required.

This raises the obvious question: **if a tool call can now hit a real, non-deterministic API, in what sense is the system still "deterministic"?**

### What stays deterministic, always

Regardless of which backend is selected:

- **Decomposer** — always rule-based regex/heuristic decomposition. Never swapped for an LLM.
- **Orchestration control flow** (`orchestration/pipeline.py`) — the fixed agent sequence, the routing heuristics (`_query_is_self_contained`, `_should_skip_critic`, `_contradiction_probability`, adversarial detection), and which agents get invoked or skipped. These depend only on the query text and prior deterministic agent outputs, never on a real backend's response content.
- **Retry/backoff behavior** (`orchestration/retry_coordinator.py`, `shared/tool_base.py`'s `execute_with_retry`) — fixed policy, same for stub and real tools.
- **Budget/cost accounting** (`shared/budget.py`) — reads `ToolResult.result["tokens"]` the same way regardless of which tool produced it; a real `LLMTool` call is tracked with the exact same code path as the stub.
- **Critic's contradiction rules** (`agents/contradiction_rules.py`) — always deterministic rule tiers (keyword, numeric-divergence, negation), applied identically to stub or real Retriever/Synthesizer output.

### What becomes non-deterministic, only when opted in

- **Retriever's search results** — `RealWebSearchTool` calls a live search API; the same query can return different results on different days (or even different runs, if the underlying index changes).
- **Synthesizer's prose** — `LLMSynthesizerAgent` calls a live LLM API; sampling means the exact wording can differ run to run even for identical input claims.

### How replay/hashing handles this

`evaluation/replay.py`'s `ExecutionReplayer` and the `/api/v1/query/run` + `/api/v1/replay/compare` API routes (`api/routes/query.py`, `api/routes/replay.py`) hash a **sanitized snapshot** of each run: query, agent sequence, tool-call *outcomes* (tool name, success, retry count, structured output), and routing decisions — deliberately excluding wall-clock fields (`latency_ms`, decision `timestamp`s) that vary run to run even under the fully deterministic stub path. This was a real bug caught and fixed while building the replay/diff feature: without sanitization, even two stub-mode runs of the same query never hashed identically, which would have made "replay proves determinism" meaningless.

Given that sanitization, the practical behavior is:

- **Stub backend**: two runs of the same query produce **identical** `execution_hash` values — same routing decisions, same tool outcomes, same content. This is checkable directly: run the same query twice through `/api/v1/query/run` and diff the hashes, or use the frontend's Replay/Diff tab.
- **Real backend**: two runs of the same query will generally produce **different** `execution_hash` values, because the sanitized snapshot still includes tool *output content* (search results, LLM text), which genuinely varies. The routing decisions and agent sequence will typically still match (since those depend on query text and deterministic upstream signals, not on retrieved content) — so a real-backend divergence report will usually show identical `agent_sequence` but different tool-call outputs, which is itself informative: it isolates *which* layer is non-deterministic rather than reporting the whole run as an opaque mismatch.

In short: **determinism is a property of the orchestrator, not a property every tool is forced to have.** The pipeline still fully traces, retries, budgets, and can replay-diff a non-deterministic tool call — it just won't report two such calls as identical, which is the correct behavior, not a limitation of the replay system.

## Configuration & Deployment

### Environment
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
LOG_LEVEL=INFO
PYTHON_ENV=production
```

### Service Stack
- **API**: FastAPI (async routes, health checks)
- **DB**: PostgreSQL 16 + asyncpg
- **Cache**: Redis (optional for future scaling)
- **Worker**: Optional long-running orchestration (via Celery/RQ)
- **Docker Compose**: Multi-service orchestration with health checks

### Database
- Async-first (asyncpg driver)
- UUID primary keys
- Timezone-aware timestamps
- Alembic migrations (bootstrap + schema)
