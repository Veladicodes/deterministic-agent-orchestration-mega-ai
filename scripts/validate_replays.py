#!/usr/bin/env python3
"""Validate stored replay traces for deterministic integrity.

Produces a small JSON summary in the results/ folder for reviewer inspection.
"""

import json
from pathlib import Path
from datetime import datetime

# make local imports work
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.replay import ExecutionReplayer


def load_traces(file_path: Path):
    traces = []
    if not file_path.exists():
        print(f"No traces file at {file_path}")
        return traces

    with open(file_path) as f:
        for line in f:
            if line.strip():
                traces.append(json.loads(line))

    return traces


def main():
    traces_file = Path("results") / "traces.jsonl"
    traces = load_traces(traces_file)
    replayer = ExecutionReplayer()

    summary = {"checked": len(traces), "valid": 0, "invalid": 0, "details": []}

    for t in traces:
        trace_id = t.get("replay_id") or t.get("original_job_id")
        computed = replayer.compute_trace_hash({
            "query": t.get("query"),
            "agent_sequence": t.get("agent_sequence"),
            "tool_calls": t.get("tool_calls"),
            "state_transitions": t.get("state_transitions"),
            "execution_path": t.get("execution_path"),
        })

        match = computed == t.get("execution_hash")

        detail = {"trace_id": trace_id, "match": match, "expected": t.get("execution_hash"), "computed": computed}
        summary["details"].append(detail)

        if match:
            summary["valid"] += 1
        else:
            summary["invalid"] += 1

    out = Path("results")
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / f"replay_validation_{datetime.utcnow().date()}.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote validation summary to {out_file}")


if __name__ == "__main__":
    main()
