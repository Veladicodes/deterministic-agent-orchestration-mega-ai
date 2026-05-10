#!/usr/bin/env python3
"""Scan traces and produce adversarial mitigation summary JSON."""
import json
from pathlib import Path
from datetime import datetime


def main():
    traces_file = Path("results") / "traces.jsonl"
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"checked": 0, "mitigations": [], "timestamp": datetime.utcnow().isoformat()}

    if not traces_file.exists():
        print("No traces.jsonl found in results/")
        return

    with open(traces_file) as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)
            summary["checked"] += 1
            routing = t.get("execution_path", {})
            decisions = routing.get("routing_decisions") or t.get("execution_path", {}).get("routing_decisions") or []
            for d in decisions:
                if d.get("decision_type") == "adversarial_detected" or d.get("selected_action") == "mitigate_injection":
                    summary["mitigations"].append({"trace": t.get("replay_id"), "decision": d})

    out_file = out_dir / f"adversarial_summary_{datetime.utcnow().date()}.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote adversarial summary to {out_file}")


if __name__ == "__main__":
    main()
