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
