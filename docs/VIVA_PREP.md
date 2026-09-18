# Viva / Defense Prep

Private prep notes, not a graded deliverable. Written so answers are grounded in what the code actually does — every claim here should be verifiable by pointing at a file/line, not asserted from memory.

## Q: Why is this still called "deterministic" if you added an LLM and a real search API?

Because determinism was never a claim about every tool call — it's a claim about the **orchestrator**. Walk through `ARCHITECTURE.md`'s "Pluggable Backends and the Determinism Boundary" section:

- The Decomposer is always rule-based. Never swapped for an LLM, by design (`agents/llm_synthesizer.py`'s docstring states this explicitly).
- The routing logic in `orchestration/pipeline.py` (`_query_is_self_contained`, `_should_skip_critic`, `_contradiction_probability`) decides which agents run based on query text and prior deterministic signals — not on live tool content, in the common case (there's one edge case worth knowing: `_should_skip_critic` reads `retriever_output.metadata.get("conflicting_evidence")`, so in principle a real search result *could* change whether Critic runs — good to have this ready if pushed on it, rather than overclaiming "never").
- Retry policy, budget/cost accounting, and the Critic's contradiction rules are identical regardless of which backend produced the input.
- What actually becomes non-deterministic, and only when explicitly opted in via `Settings.use_real_backends`: the Retriever's search results and the Synthesizer's generated prose.

**One-sentence answer**: "Determinism lives in the control plane — the sequence, the routing, the retry/budget bookkeeping, the replay hashing — not in forcing every tool to return the same bytes every time. That's a design choice, not a compromise: it's exactly what lets you add a real LLM without losing the ability to audit *why* the pipeline made the decisions it made."

## Q: Why not use an LLM as the Critic (contradiction judge)?

The project's own original design rationale (`README.md`'s "Design Decisions") already argues this: LLM scores vary per API version, making baselines unstable, and a black-box judge can't be debugged when it's wrong. That's still true. Instead of reaching for an LLM judge to fix the Critic's real weakness (a fixed antonym keyword list), `agents/contradiction_rules.py` adds two new deterministic, independently-testable tiers:

- **Numeric-divergence**: catches conflicting numeric claims about the same subject (e.g. "76%" vs "91%" accuracy) that the keyword list couldn't see at all.
- **Negation-aware**: catches a claim and its negated form sharing a keyword ("improved" vs "did not improve").

Both return structured evidence (`{"rule": ..., "subject": ..., "value_a": ..., "value_b": ...}`) that gets rendered into a human-readable `CritiqueRecord.details` string — so every flagged contradiction stays auditable, unlike an LLM judge's free-text rationale. `tests/test_contradiction_rules.py` locks in the exact boundary behavior (e.g. `NUMERIC_DIVERGENCE_THRESHOLD = 8.0` points).

**Good follow-up to have ready**: "What's still missing?" — genuine confidence-interval/Bayesian contradiction reasoning (BENCHMARKS.md's limitation #3), which is a different, harder problem than what these two tiers solve.

## Q: What's the actual novel contribution here, versus just wrapping API calls?

Three concrete things, each demoable live:

1. **Automatic cost/budget instrumentation for any new tool, with zero changes to the budget system.** `shared/agent_base.py`'s `BaseAgent.execute_tool()` reads `ToolResult.result["tokens"]` and forwards it to `BudgetManager.consume()`. When `tools/llm_tool.py` was added, it just had to put a `tokens` key in its result dict — no changes to `shared/budget.py` were needed for real LLM cost tracking to work. **Live demo**: show `shared/budget.py` is untouched in the diff, then show `tests/test_llm_synthesizer.py::test_llm_synthesizer_records_budget_consumption` passing.
2. **A replay/diff system that survived contact with its own non-determinism bug.** While building `/api/v1/query/run` + `/api/v1/replay/compare`, the first version hashed wall-clock `latency_ms` and decision timestamps — meaning even two runs of the *fully deterministic stub pipeline* never hashed identically. This was caught by `tests/test_api_routes.py::test_identical_queries_produce_identical_hashes_in_stub_mode` failing, not assumed away. The fix (`api/routes/query.py`'s `sanitize_tool_calls`/`sanitize_routing_decisions`) is a good story about what "testing the thing you built, not just that it runs" looks like. **Live demo**: run the same query twice via the frontend's Replay/Diff tab, show `identical: true`.
3. **The retry/backoff coordinator and exponential-backoff policy** (`orchestration/retry_coordinator.py`) — orchestration-level retry logic decoupled from any individual tool, tested independently of what tool is plugged in.

## Q: How would this scale / what would you change for production?

Honest answer, in order of what actually matters:
- **Token-level LLM streaming isn't implemented.** `/api/v1/query/stream`'s SSE events are stage-level (`agent_started`/`agent_completed`), not token-level — `tools/llm_tool.py`'s `LLMTool.run()` returns one complete `ToolResult`, not a stream. Implementing that would need a separate streaming method on the tool interface.
- **The in-memory rate limiter (`api/middleware/rate_limit.py`) is single-instance only** — a real multi-instance deployment would need a shared store (Redis, which is already in the stack) instead of an in-process dict.
- **`worker/` (Celery) is provisioned in `docker-compose.yml` but nothing actually enqueues a task today** — no code path calls `.delay()`/`.apply_async()`. It's there for future long-running-job support, not currently load-bearing.
- **Search result caching** would cut both cost and latency for repeated queries under the real backend — not implemented.

## Q: Walk me through what happens when I ask a query.

Use `docs/example_pipeline_walkthrough.md` as the base narrative, but be ready to point at the actual code for each step:
1. `orchestration/pipeline.py::PipelineRunner.run()` creates a `SharedContext`, always runs `DecomposerAgent` first (`agents/decomposer.py` — regex intent/entity/ambiguity detection).
2. Deterministic routing (`_query_is_self_contained`, `_detect_adversarial_in_query`, `_contradiction_probability`) decides whether Retriever and Critic run at all — this is itself logged as `RoutingDecision` records, visible in `execution_trace.routing_decisions` and streamed live as `routing_decision` SSE events.
3. If invoked, `RetrieverAgent` does 2-hop retrieval via whichever `web_search_tool` was injected (stub by default, `RealWebSearchTool` if opted in) — `agents/retriever.py`.
4. If invoked, `CriticAgent` runs the three contradiction-rule tiers plus confidence scoring — `agents/critic.py` + `agents/contradiction_rules.py`.
5. `SynthesizerAgent` (or `LLMSynthesizerAgent`) builds the final answer from non-flagged claims, with provenance links preserved — `agents/synthesizer.py` / `agents/llm_synthesizer.py`.
6. `ResultAssembler` (`orchestration/result_assembler.py`) collects everything into a `PipelineResult`, and `ExecutionReplayer` (`evaluation/replay.py`) can hash/replay/diff the resulting trace.

## Scripted live-demo sequence (have this ready, don't improvise on the day)

1. **Deterministic baseline**: run `"What is machine learning?"` via the frontend's Run tab. Show the stage timeline (retriever/critic skipped — point at the routing decision reasons shown live).
2. **Replay proof**: switch to the Replay/Diff tab, run the same query twice, show `identical: true` with matching hashes.
3. **Real backend** (only if you have live API keys configured and are comfortable with the cost): set `USE_REAL_BACKENDS=true`, rerun the same query, show the answer is now LLM-generated prose, and that a second real-backend run produces a *different* hash (open the divergence list) — this is the moment to say the line from ARCHITECTURE.md: "determinism is a property of the orchestrator, not something every tool is forced to have."
4. **Contradiction catch**: run `contradiction_prone_006`'s query ("Is model accuracy 76% or 91% according to the benchmark?") and show the Critic flags it via the numeric-divergence rule, with the evidence (`subject`, `value_a`, `value_b`, `divergence`) visible in the critique.

## Known soft spots — don't get caught flat-footed

- **Git history is a single day for the original core, then this session's incremental work on top.** Be upfront about this if asked (see the commit-history discussion in the project's elevation plan) — the honest framing is "the deterministic core was a focused initial build; the backend/frontend/eval work on top of it happened in a separate, later pass." Don't imply a multi-week continuous effort that didn't happen.
- **No live deployment exists** unless you've since followed `docs/DEPLOYMENT.md` and actually deployed it. Don't claim a live URL that isn't real.
- **`--backend real` has never been run with a live key in this environment** (see BENCHMARKS.md's "Real Backend Results" section) — the code and tests are real and verified via mocks, but there are no live-traffic numbers yet. Say so plainly if asked; don't imply measured real-backend benchmarks exist.
