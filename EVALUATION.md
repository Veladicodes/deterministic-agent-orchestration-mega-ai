# Evaluation Framework (concise)

This document specifies what the evaluation does, why, and how reviewers can reproduce results quickly.

Summary
- Focus: reproducible behavioral evidence (decomposition, retrieval, provenance, contradiction handling).
- Dataset: 40 queries in five categories (normal, ambiguous, adversarial, contradiction_prone, provenance_sensitive).
- Outputs: per-run metadata, aggregated summary, traces.jsonl of per-query replay traces.

Design principles
- Rule-driven determinism: identical input → identical orchestration and traces.
- Behavioral targets (not exact-text correctness): measure properties such as provenance coverage and contradiction detection.
- Lightweight realism: deterministic stubbed tools, multi-hop retrieval, retry/fallback tracing.

Dataset
- See `data/evaluation_dataset.json` for queries and behavioral expectations.

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
python scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/
python scripts/validate_replays.py
python scripts/generate_report.py --evaluation-id {eval_id} --format markdown
```

Reviewer checks (fast)
- Confirm deterministic run: `python scripts/validate_replays.py` → zero mismatches.
- Inspect `results/{eval_id}/traces.jsonl` for `execution_path.routing_decisions` and `retrieval_trace`.
- Use SSE demo: start the API and POST to `/api/v1/query/stream` with `{ "query": "..." }` to watch incremental orchestration events.

Limitations
- Rule-based evaluation trades nuanced model judgment for reproducibility; interpret quality metrics accordingly.

This file is intentionally terse — details for metrics and trace formats are in `evaluation/schemas.py` and the `scripts/` helpers.
