#!/usr/bin/env python3
"""Run a quick local streaming demo using PipelineRunner event_sink.

Prints a small number of events to the console so reviewers can observe streaming.
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestration.pipeline import PipelineRunner


async def main():
    query = "What is machine learning?"
    events = []

    async def sink(e):
        ts = datetime.utcnow().isoformat()
        e["ts"] = ts
        events.append(e)
        # Print compact summary
        print(json.dumps({"ts": ts, "event_type": e.get("event_type"), "summary": e.get("trigger_reason") or e.get("selected_action") or e.get("tool")}, ensure_ascii=False))

    runner = PipelineRunner()
    await runner.run(query, event_sink=sink)

    print("--- demo complete: wrote events count", len(events))


if __name__ == "__main__":
    asyncio.run(main())
