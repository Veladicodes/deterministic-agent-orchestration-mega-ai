#!/usr/bin/env python3
"""Run a deterministic baseline pipeline: decomposer -> retriever -> synthesizer.

Saves results to `results/{run_id}/` similarly to run_evaluation.py.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.dataset import EvaluationDataset
from shared.logging import get_logger
from orchestration.result_assembler import ResultAssembler
from context.shared_context import SharedContext
from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from agents.decomposer import DecomposerAgent
from agents.retriever import RetrieverAgent
from agents.synthesizer import SynthesizerAgent
from shared.agent_base import AgentConfig
from evaluation.runner import EvaluationRunner
from evaluation.replay import ExecutionReplayer

logger = get_logger("eval_cli.baseline")


async def run_baseline_async(dataset: EvaluationDataset, output_dir: Path):
    runner = EvaluationRunner(dataset)
    runner.initialize()

    for entry in dataset.all_entries():
        query_id = entry["query_id"]
        query = entry["input_query"]
        logger.info(f"Baseline processing {query_id}")

        # Build minimal context
        context = SharedContext(job_id=query_id, original_query=query)
        budget = BudgetManager()
        exec_logger = ExecutionLogger()

        # Decomposer
        dec_cfg = AgentConfig(agent_id="decomposer")
        dec_agent = DecomposerAgent(config=dec_cfg, budget_manager=budget, exec_logger=exec_logger)  # type: ignore
        dec_out = await dec_agent.run(context)

        # Retriever
        ret_cfg = AgentConfig(agent_id="retriever")
        ret_agent = RetrieverAgent(config=ret_cfg, budget_manager=budget, exec_logger=exec_logger)  # type: ignore
        ret_out = await ret_agent.run(context)

        # Synthesizer
        synth_cfg = AgentConfig(agent_id="synthesizer")
        synth_agent = SynthesizerAgent(config=synth_cfg, budget_manager=budget, exec_logger=exec_logger)  # type: ignore
        synth_out = await synth_agent.run(context)

        # Assemble minimal result
        assembler = ResultAssembler(query_id)
        # Attach final answer
        context.final_answer = synth_out.final_answer if hasattr(synth_out, "final_answer") else str(synth_out)
        result = assembler.assemble(context, True, 0.0, datetime.utcnow(), datetime.utcnow())

        # Add to evaluation runner metrics
        # Simplified: use runner.add_query_result to collect counts
        from evaluation.metrics import PipelineMetrics

        metrics = PipelineMetrics(
            job_id=query_id,
            total_latency_ms=0.0,
            timestamp=datetime.utcnow(),
        )
        runner.add_query_result(query_id, metrics, failures=[])

    metadata = runner.complete()
    run_dir = output_dir / metadata.evaluation_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Save a lightweight summary
    with open(run_dir / "baseline_summary.json", "w") as f:
        json.dump({"evaluation_run_id": metadata.evaluation_run_id, "query_count": metadata.query_count}, f, indent=2, default=str)

    logger.info(f"Baseline run saved to {run_dir}")


def main():
    parser = argparse.ArgumentParser(description="Run baseline pipeline")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.dataset.exists():
        logger.error("Dataset not found")
        sys.exit(1)

    dataset = EvaluationDataset(str(args.dataset))
    dataset.load()

    asyncio.run(run_baseline_async(dataset, args.output))


if __name__ == "__main__":
    main()
