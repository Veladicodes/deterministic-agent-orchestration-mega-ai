#!/usr/bin/env python3
"""
Replay and validate execution traces.

Usage:
    python scripts/replay_query.py --trace-id job_001 --operation validate --traces-dir results/
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation import ExecutionReplayer, ReplayTrace
from shared.logging import get_logger

logger = get_logger("eval_cli.replay_query")


def load_traces(traces_file: Path) -> dict:
    """Load traces from JSONL file."""
    traces = {}
    if not traces_file.exists():
        logger.warning(f"Traces file not found: {traces_file}")
        return traces

    with open(traces_file) as f:
        for line in f:
            if line.strip():
                trace_dict = json.loads(line)
                trace_id = trace_dict.get("replay_id") or trace_dict.get("original_job_id")
                traces[trace_id] = trace_dict

    logger.info(f"Loaded {len(traces)} traces from {traces_file}")
    return traces


def validate_operation(replayer: ExecutionReplayer, trace_dict: dict) -> dict:
    """Validate a trace."""
    # Convert dict to ReplayTrace (simplified)
    try:
        is_valid = (
            trace_dict.get("replay_id") is not None
            and trace_dict.get("agent_sequence") is not None
            and trace_dict.get("execution_path") is not None
        )

        if is_valid:
            logger.info(
                f"Trace {trace_dict.get('replay_id')} is valid: {len(trace_dict.get('agent_sequence', []))} agents"
            )
            return {
                "trace_id": trace_dict.get("replay_id"),
                "valid": True,
                "agent_count": len(trace_dict.get("agent_sequence", [])),
                "tool_call_count": len(trace_dict.get("tool_calls", [])),
            }
        else:
            logger.warning(f"Trace {trace_dict.get('replay_id')} is missing required fields")
            return {
                "trace_id": trace_dict.get("replay_id"),
                "valid": False,
                "reason": "missing required fields",
            }
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {
            "trace_id": trace_dict.get("replay_id"),
            "valid": False,
            "reason": str(e),
        }


def compare_operation(replayer: ExecutionReplayer, trace_dict: dict, baseline_dict: dict) -> dict:
    """Compare two traces for divergence."""
    try:
        trace1_agents = trace_dict.get("agent_sequence", [])
        trace2_agents = baseline_dict.get("agent_sequence", [])

        diverged = trace1_agents != trace2_agents

        result = {
            "trace1_id": trace_dict.get("replay_id"),
            "trace2_id": baseline_dict.get("replay_id"),
            "diverged": diverged,
            "trace1_agents": len(trace1_agents),
            "trace2_agents": len(trace2_agents),
            "trace1_tools": len(trace_dict.get("tool_calls", [])),
            "trace2_tools": len(baseline_dict.get("tool_calls", [])),
        }

        if diverged:
            logger.warning("Traces diverged in agent sequence")
        else:
            logger.info("Traces are identical")

        return result
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        return {"error": str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Replay and validate execution traces")
    parser.add_argument(
        "--trace-id",
        required=True,
        help="Trace ID to operate on",
    )
    parser.add_argument(
        "--operation",
        required=True,
        choices=["validate", "compare"],
        help="Operation to perform",
    )
    parser.add_argument(
        "--baseline-id",
        help="Baseline trace ID for comparison (required for --operation compare)",
    )
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing trace files",
    )
    parser.add_argument(
        "--evaluation-id",
        help="Evaluation run ID (if traces are in subdirectory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    replayer = ExecutionReplayer()

    # Build path to traces file
    if args.evaluation_id:
        traces_file = args.traces_dir / args.evaluation_id / "traces.jsonl"
    else:
        traces_file = args.traces_dir / "traces.jsonl"

    # Load traces
    traces = load_traces(traces_file)

    if args.operation == "validate":
        if args.trace_id not in traces:
            logger.error(f"Trace not found: {args.trace_id}")
            sys.exit(1)

        result = validate_operation(replayer, traces[args.trace_id])
        print(json.dumps(result, indent=2))

    elif args.operation == "compare":
        if not args.baseline_id:
            logger.error("--baseline-id required for compare operation")
            sys.exit(1)

        if args.trace_id not in traces:
            logger.error(f"Trace not found: {args.trace_id}")
            sys.exit(1)

        if args.baseline_id not in traces:
            logger.error(f"Baseline trace not found: {args.baseline_id}")
            sys.exit(1)

        result = compare_operation(replayer, traces[args.trace_id], traces[args.baseline_id])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
