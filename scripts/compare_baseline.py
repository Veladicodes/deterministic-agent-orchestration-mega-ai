#!/usr/bin/env python3
"""Compare baseline and orchestrated evaluation runs and write a concise JSON+MD summary."""
import argparse
import json
from pathlib import Path
from datetime import datetime

def load_json(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Compare baseline and orchestrated runs")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--orchestrated", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    baseline = load_json(args.baseline / "summary.json")
    orchestrated = load_json(args.orchestrated / "summary.json")

    comparison = {
        "baseline": baseline is not None,
        "orchestrated": orchestrated is not None,
        "timestamp": datetime.utcnow().isoformat(),
        "differences": [],
    }

    if baseline and orchestrated:
        # Compare provenance_coverage and completion_rate and p95
        b_pc = baseline.get("avg_provenance_coverage") or baseline.get("provenance_coverage") or 0.0
        o_pc = orchestrated.get("avg_provenance_coverage") or orchestrated.get("provenance_coverage") or 0.0
        comparison["differences"].append({"metric": "provenance_coverage", "baseline": b_pc, "orchestrated": o_pc})

        b_comp = baseline.get("completion_rate") or 0.0
        o_comp = orchestrated.get("completion_rate") or 0.0
        comparison["differences"].append({"metric": "completion_rate", "baseline": b_comp, "orchestrated": o_comp})

        b_p95 = baseline.get("p95_latency_ms") or 0.0
        o_p95 = orchestrated.get("p95_latency_ms") or 0.0
        comparison["differences"].append({"metric": "p95_latency_ms", "baseline": b_p95, "orchestrated": o_p95})

    args.out.mkdir(parents=True, exist_ok=True)
    out_file = args.out / f"baseline_comparison_{datetime.utcnow().date()}.json"
    with open(out_file, "w") as f:
        json.dump(comparison, f, indent=2)

    # Write short markdown
    md = ["# Baseline Comparison\n", f"Generated: {comparison['timestamp']}\n\n"]
    for d in comparison["differences"]:
        md.append(f"- **{d['metric']}**: baseline={d['baseline']}, orchestrated={d['orchestrated']}\n")

    with open(args.out / "BENCHMARK_COMPARISON.md", "w") as f:
        f.writelines(md)

    print(f"Wrote comparison to {out_file} and BENCHMARK_COMPARISON.md")


if __name__ == "__main__":
    main()
