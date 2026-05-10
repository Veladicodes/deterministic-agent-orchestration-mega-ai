#!/bin/bash

set -euo pipefail

echo "MULTI-AGENT ORCHESTRATION DEMO"
echo "--------------------------------"

for cmd in python make docker; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required command: $cmd"
        exit 1
    fi
done

echo "[1/5] Starting services"
make up

echo "[2/5] Running migrations"
make migrate

echo "[3/5] Running tests"
make test

echo "[4/5] Running evaluation"
python scripts/run_evaluation.py --dataset data/evaluation_dataset.json --output results/

LATEST_RUN=$(python - <<'PY'
from pathlib import Path
results = Path("results")
runs = [p for p in results.iterdir() if p.is_dir()]
print(sorted(runs, key=lambda p: p.stat().st_mtime)[-1].name if runs else "")
PY
)

if [ -n "$LATEST_RUN" ]; then
    echo "[5/5] Generating reports and replay summary"
    python scripts/generate_report.py --evaluation-id "$LATEST_RUN" --format markdown --results-dir results --output-dir results/$LATEST_RUN
    python scripts/replay_query.py --trace-id normal_001 --operation validate --traces-dir results --evaluation-id "$LATEST_RUN"
    echo "Latest run: results/$LATEST_RUN"
    echo "Report: results/$LATEST_RUN/report.md"
    echo "Failure report: results/$LATEST_RUN/failure_report.md"
else
    echo "No evaluation run found in results/"
    exit 1
fi

echo "Demo complete"
