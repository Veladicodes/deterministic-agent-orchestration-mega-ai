A Multi-Agent Orchestration System

A deterministic, operationally credible orchestration framework for multi-agent execution with full execution tracing, replayability, and behavioral evaluation.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![Tests](https://img.shields.io/badge/tests-81%20passing-brightgreen)
![Execution](https://img.shields.io/badge/execution-deterministic-orange)
![Replay](https://img.shields.io/badge/replay-validated-blueviolet)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## What This Is

This project demonstrates how to build an operationally credible multi-agent orchestration framework that prioritizes:

- **Deterministic execution** - Same input produces identical output, enabling reproducibility
- **Observability** - Full execution traces, state transitions, and metrics
- **Replayability** - Reproduce and debug any past execution
- **Evaluation** - Behavioral assessment with failure analysis
- **Traceability** - Where every claim comes from and why it was made

This is a systems engineering exercise, not an AI platform. The agents are rule-based. Orchestration is deterministic. Evaluation is behavioral, not LLM-based.

## Why This Project Exists

The repository is meant to show how far a deterministic orchestration design can go before adding semantic retrieval, model-driven routing, or agent autonomy. The goal is not to simulate intelligence. The goal is to make every execution understandable, replayable, and easy to validate.

## System Goals

The system executes a fixed pipeline on user queries:

```
Query → Decompose → Retrieve → Critique → Synthesize → Result
```

Each step is:
- **Observable**: Full logging and execution traces
- **Testable**: Deterministic behavior
- **Reproducible**: Replay any past execution
- **Traceable**: Provenance-linked claims
- **Analyzable**: Structured failure classification

## Architecture Overview

| Layer | Responsibility |
|-------|---|
| **Contracts** | Pydantic schemas for all data structures |
| **Tools** | Retrieval, code execution, reflection, database queries |
| **Agents** | DecomposerAgent, RetrieverAgent, CriticAgent, SynthesizerAgent |
| **Orchestration** | ExecutionStateManager, RetryCoordinator, ResultAssembler, PipelineRunner |
| **Persistence** | SQLAlchemy ORM, async repositories, Alembic migrations |
| **Evaluation** | Dataset, metrics, failure analysis, replay, reporting |
| **API** | FastAPI HTTP layer, async endpoints |

Full details: [ARCHITECTURE.md](ARCHITECTURE.md)

## Execution Pipeline

The deterministic agent sequence:

### 1. **Decomposer Agent**
Breaks complex queries into sub-tasks.
- Input: User query
- Output: Decomposed query structure with dependencies
- Example: "Compare PostgreSQL and Redis" → retrieve properties, compare features, discuss tradeoffs

### 2. **Retriever Agent**
Gathers evidence via tool calls.
- Input: Decomposed sub-tasks
- Output: Retrieved results with provenance records
- Triggers retries on failure (up to 3 attempts with exponential backoff)

### 3. **Critic Agent**
Analyzes evidence for contradictions and gaps.
- Input: Retrieved results
- Output: Contradiction flags, confidence scores, provenance assessment
- Rule-based analysis: detects boolean conflicts, confidence issues, source quality

### 4. **Synthesizer Agent**
Assembles final answer with provenance attribution.
- Input: Critique analysis
- Output: Structured answer, confidence score, provenance links
- Removes low-confidence claims, surfaces ambiguity

All execution is traced and persisted for replay and evaluation.

## Core Features

- Deterministic multi-agent pipeline with fixed execution order
- Full execution tracing and replayability for every run
- Structured evaluation with failure classification and reporting
- Provenance-linked outputs to keep claims auditable

## Benchmark Snapshot

| Metric | Result |
|---|---|
| Queries Evaluated | 40 |
| Replay Validation | Pass |
| Provenance Coverage | 100% |
| Tests Passing | 81 |
| Deterministic Replay | Verified |

![Evaluation snapshot](docs/evaluation_snapshot.svg)

## Quickstart

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 16 (via Docker)

### Run the System

```bash
# 1. Setup
make up                 # Start database and services
make migrate            # Run migrations

# 2. Validate
make test               # Run 81 tests (all passing)

# 3. Evaluate
python scripts/run_evaluation.py \
  --dataset data/evaluation_dataset.json \
  --output results/

# 4. View results
# Check results/<evaluation_run_id>/report.md

```


### Reviewer demo (minimal)

```bash
docker compose up -d --build
python scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/
python scripts/replay_query.py --trace-id normal_001 --operation validate --evaluation-id <run_id>
```

### Run Individual Evaluation Tools

```bash
# Replay a specific execution
python scripts/replay_query.py \
  --trace-id normal_001 \
  --operation validate \
  --evaluation-id <run_id>

# Generate reports from results
python scripts/generate_report.py \
  --evaluation-id <run_id> \
  --format markdown
```

### Run Tests

```bash
make test               # All 81 tests
make test-agents        # Agent tests only
make test-eval          # Evaluation tests only
```

## Evaluation System

This system includes a **behavioral evaluation framework** that avoids exact-match validation:

### Dataset
- **40 queries** across 5 categories (normal, ambiguous, adversarial, contradiction-prone, provenance-sensitive)
- **Behavioral expectations** (not exact answers)
- **Curated for realistic challenges**

### Metrics
- **Pipeline metrics**: Latency, retries, completion rate
- **Quality metrics**: Provenance coverage, contradiction detection, confidence score
- **Failure classification**: 10 failure types with deterministic rules

### Replay
- Every execution creates an immutable trace
- Replay deterministically reconstructs past execution
- Compare traces to detect divergence or validate fixes

### Reporting
- JSON summaries
- Markdown reports with tables
- Failure analysis and weak areas identification

The current local benchmark run completes all 40 queries, produces replayable traces, and validates trace integrity. It is a system-behavior check, not a measure of semantic search quality.

Full details: [EVALUATION.md](EVALUATION.md), [BENCHMARKS.md](BENCHMARKS.md)

## Design Decisions

### Why Deterministic Orchestration?

**Decision**: Fixed sequential agent pipeline (no autonomous loops, no dynamic orchestration)

**Rationale**:
- Determinism enables reproducibility and debugging
- Reduces surface area for bugs
- Simplifies operation and monitoring
- Makes failure modes visible and analyzable

**Tradeoff**: Less flexibility than dynamic orchestration, but vastly better observability

### Why No LangChain / AutoGen / Embeddings?

**Rationale**:
- Those frameworks optimize for convenience, not understanding
- Our goal is reproducibility and traceability, not rapid prototyping
- Deterministic rule-based execution is easier to audit
- Reduces black-box behavior and complexity

**Tradeoff**: More code, but all of it is reviewable and understandable

### Why No LLM-Based Evaluation?

**Rationale**:
- LLM scores vary per API version, making baselines unstable
- Behavioral evaluation avoids brittleness
- Rule-based failure classification is deterministic and debuggable

**Tradeoff**: No nuanced quality assessment, but reproducible results and no dependency on external APIs

### Why Rule-Based Critique?

**Rationale**:
- Deterministic, debuggable contradiction detection
- Consistent behavior enables testing and monitoring
- Failures are explicit and classifiable

**Tradeoff**: Simpler than semantic analysis, but sufficient for many cases and fully transparent

## Known Limitations

### Provenance Specificity
Cannot reliably locate specific academic papers or benchmarks. Retriever returns general information instead of precise sources.
- **Impact**: 40% failure on provenance-sensitive queries
- **Fix**: Integrate arXiv API, Google Scholar integration

### Ambiguity Handling
Decomposer uses keyword patterns, not semantic understanding. Misses some ambiguous interpretations.
- **Impact**: 10% failure on ambiguous queries
- **Fix**: Semantic-aware decomposition (requires embeddings or LLM)

### Simple Contradiction Detection
Critic detects boolean conflicts (A vs ¬A) but struggles with probabilistic contradictions (confidence intervals).
- **Impact**: Rare in practice, but possible edge case
- **Fix**: Bayesian reasoning in Critic

### Synthesis Overconfidence
Low-confidence results aren't surfaced to users. Answer templates always sound assertive.
- **Impact**: Users may not see uncertainty
- **Fix**: Include confidence in API response; surface to UI

### Tool Response Failures
If a tool times out or returns malformed data, retry logic is at orchestration layer, not tool layer.
- **Impact**: ~1–2% query failure rate from tool issues
- **Fix**: Circuit breaker pattern on tool invocation

**Philosophy**: We document limitations honestly. This increases credibility.

## Repository Structure

```
mega-ai/
├── agents/                 # Agent implementations (Decomposer, Retriever, Critic, Synthesizer)
├── api/                    # FastAPI HTTP layer
├── context/                # Shared context and data structures
├── data/                   # evaluation_dataset.json (40 curated queries)
├── db/                     # SQLAlchemy ORM, Alembic migrations
├── evaluation/             # Evaluation framework (metrics, failure analysis, replay, reporting)
├── orchestration/          # ExecutionStateManager, PipelineRunner
├── shared/                 # Logging, configuration, utilities
├── tools/                  # Retrieval, code execution, reflection tools
├── tests/                  # 81 unit and integration tests
├── scripts/                # CLI tools (run_evaluation, replay_query, generate_report)
├── notebooks/              # evaluation_eda.ipynb (analysis notebook)
├── docs/                   # Architecture diagram, example walkthrough
├── ARCHITECTURE.md         # Detailed system design
├── EVALUATION.md           # Evaluation philosophy and framework
├── BENCHMARKS.md           # Baseline results and known weaknesses
└── Makefile                # Common commands
```

## Running Locally

### 1. Setup Environment

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start Services

```bash
docker-compose up -d       # Start PostgreSQL and Redis
make migrate               # Run migrations
```

### 3. Run Tests

```bash
pytest tests/ -v           # All 81 tests
```

### 4. Run Evaluation

```bash
python scripts/run_evaluation.py \
  --dataset data/evaluation_dataset.json \
  --output results/
```

## API Endpoints

See [api/](api/) for FastAPI application.

```bash
# Start API server
python -m api.main

# Health check
curl http://localhost:8000/health
```

## Testing

- **81 tests** covering agents, orchestration, persistence, and evaluation
- All tests deterministic and reproducible
- Test structure: `tests/test_<module>.py`

```bash
make test                  # Run all tests
make test-agents           # Agent tests
make test-orchestration    # Orchestration tests
make test-eval             # Evaluation tests
```

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System design, execution flow, tradeoffs
- **[EVALUATION.md](EVALUATION.md)**: Evaluation framework, metrics, dataset design
- **[BENCHMARKS.md](BENCHMARKS.md)**: Baseline results, known limitations, operational thresholds
- **[docs/architecture_diagram.md](docs/architecture_diagram.md)**: Text diagrams
- **[docs/example_pipeline_walkthrough.md](docs/example_pipeline_walkthrough.md)**: Full execution example

## Engineering Philosophy

This project embodies:

✅ **Observability**: Every operation is logged and traced  
✅ **Reproducibility**: Deterministic execution enables replay  
✅ **Traceability**: Provenance linked to every claim  
✅ **Honesty**: Limitations documented, not hidden  
✅ **Testability**: 81 tests, all passing  
✅ **Simplicity**: No unnecessary abstractions  

## What This Is Not

This is not an AI research project, a framework demo, or a production SaaS. It is a disciplined engineering exercise that prioritizes understanding, reproducibility, and operational clarity over flexibility.

## License

MIT
