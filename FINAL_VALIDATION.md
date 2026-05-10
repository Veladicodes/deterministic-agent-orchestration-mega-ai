Final validation and demo instructions

- Run the reviewer demo: `make demo` (or `python scripts/run_evaluation.py ...` for finer control).
- Artifacts produced (results/): evaluation summaries, traces.jsonl, replay_validation_YYYY-MM-DD.json, baseline_comparison, adversarial_summary.
- Use `scripts/sse_demo.py` to observe streaming events locally.
- If environment variables are missing, set minimal stubs or run demo on the provided deterministic dataset.
