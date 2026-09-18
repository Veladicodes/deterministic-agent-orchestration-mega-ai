# Evaluation Framework (concise)

This document specifies what the evaluation does, why, and how reviewers can reproduce results quickly.

Summary
- Focus: reproducible behavioral evidence (decomposition, retrieval, provenance, contradiction handling).
- Dataset: 44 queries in five categories (normal, ambiguous, adversarial, contradiction_prone, provenance_sensitive) — see "Dataset v1.1" below for what was added and why.
- Outputs: per-run metadata, aggregated summary, traces.jsonl of per-query replay traces.

Design principles
- Rule-driven determinism: identical input → identical orchestration and traces.
- Behavioral targets (not exact-text correctness): measure properties such as provenance coverage and contradiction detection.
- Lightweight realism: deterministic stubbed tools, multi-hop retrieval, retry/fallback tracing.

Dataset
- See `data/evaluation_dataset.json` for queries and behavioral expectations.

### Dataset v1.1 (4 new entries)

Added alongside the real-backend and contradiction-rule work:

- `provenance_sensitive_006`, `provenance_sensitive_007` — regression tests for the documented "Provenance Specificity" weakness (BENCHMARKS.md). Both ask for a specific, independently-verifiable fact (a paper's reported accuracy, a paper's publication year) that the deterministic stub retriever cannot locate (it returns generic hash-based snippets, not real search results) but `RealWebSearchTool` should be able to, once run with `--backend real` and a live key.
- `normal_011` — targets LLM-synthesis fluency: run once under each synthesizer backend (`--backend stub` vs `--backend real`) to compare the deterministic string-concatenation answer against the LLM-generated prose for the same filtered claim pool.
- `contradiction_prone_006` — regression test for the numeric-divergence contradiction tier added in `agents/contradiction_rules.py`. Before that tier existed, two conflicting numeric claims about the same subject (e.g. "76%" vs "91%" accuracy) were invisible to the Critic's fixed antonym-keyword list; this query's two retrieved values are constructed to exceed `NUMERIC_DIVERGENCE_THRESHOLD` and should now be flagged. Unit-level coverage for the rule itself lives in `tests/test_contradiction_rules.py`; this dataset entry exercises it through the full pipeline.

Key metrics (collected per query and aggregated)
- Latency: avg, p50, p95, p99, max
- Operational: completion_rate, total_retries, replay_divergence_rate
- Quality: provenance_coverage, contradiction_detection_rate, synthesis_completeness, confidence_score
- Failure breakdown by type and agent

Replayability
- Each query emits a `ReplayTrace` with agent_sequence, tool_calls, state_transitions, execution_path, and a deterministic `execution_hash`.
- Use `scripts/validate_replays.py` to recompute trace hashes and produce `results/replay_validation_YYYY-MM-DD.json`.

Running a full evaluation
```bash
python scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/ --backend stub
python scripts/validate_replays.py
python scripts/generate_report.py --evaluation-id {eval_id} --format markdown
```

`--backend` (default `stub`) selects the tool configuration; see "Stub vs. real backend methodology" below.

Reviewer checks (fast)
- Confirm deterministic run: `python scripts/validate_replays.py` → zero mismatches.
- Inspect `results/{eval_id}/traces.jsonl` for `execution_path.routing_decisions` and `retrieval_trace`.
- Use SSE demo: start the API and POST to `/api/v1/query/stream` with `{ "query": "..." }` to watch incremental orchestration events (see `docs/SSE_EVENTS.md` for the full event vocabulary), or use `frontend/`'s Run tab for the same thing visually.
- Cross-run reproducibility: POST the same query twice to `/api/v1/query/run` and compare `execution_hash` (or use the frontend's Replay/Diff tab) — should match exactly under `--backend stub`.

## Stub vs. real backend methodology

`--backend stub` (default) uses the deterministic tools (`tools/web_search.py`, `SynthesizerAgent`) and produces the reproducible baseline numbers in BENCHMARKS.md. `--backend real` opts into `RealWebSearchTool` (Tavily) and `LLMSynthesizerAgent` (Anthropic) — genuinely non-deterministic, since live search results and LLM sampling vary run to run.

**These two configurations must always be reported as separate result sets, never averaged together.** A run under `--backend real` tags every query's `PipelineMetrics.metadata` with `backend: "real"`, plus `cost_usd` and `llm_tokens` summed from the tool calls' raw output payloads (`orchestration/result_assembler.py` threads each `ToolCallRecord.output` — including `LLMTool`'s `tokens`/`cost_usd` fields — into `execution_trace["tool_calls"]` with no database schema change). BENCHMARKS.md's "Real Backend Results" section is the place these numbers get published once a run has actually been made with live API keys; see that section for current status (no live run has been made in this environment — methodology only, not fabricated numbers).

Limitations
- Rule-based evaluation trades nuanced model judgment for reproducibility; interpret quality metrics accordingly.
- `--backend real` numbers are not reproducible run-to-run by design (live search/LLM content varies); only `agent_sequence`/routing-decision agreement, not full `execution_hash` equality, should be expected to hold across two real-backend runs of the same query (see ARCHITECTURE.md's "Pluggable Backends and the Determinism Boundary").

This file is intentionally terse — details for metrics and trace formats are in `evaluation/schemas.py` and the `scripts/` helpers.
