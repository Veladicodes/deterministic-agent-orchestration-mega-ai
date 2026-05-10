"""PipelineRunner implementation.

Main orchestrator for deterministic sequential agent execution.
Executes: Decomposer -> Retriever -> Critic -> Synthesizer
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Optional, Callable, Awaitable, Any

from shared.agent_base import AgentConfig
from shared.budget import BudgetManager
from shared.exec_logger import ExecutionLogger
from shared.enums import ExecutionStatus
from shared.logging import get_logger
from context.shared_context import SharedContext, AgentOutput
from agents.decomposer import DecomposerAgent
from agents.retriever import RetrieverAgent
from agents.critic import CriticAgent
from agents.synthesizer import SynthesizerAgent
from tools.self_reflection import SelfReflectionTool
from orchestration.schemas import PipelineResult, AgentExecutionEvent
from orchestration.state_manager import ExecutionStateManager
from orchestration.retry_coordinator import RetryCoordinator, RetryConfig
from orchestration.result_assembler import ResultAssembler


class PipelineRunner:
    """Deterministic sequential pipeline orchestrator.

    Executes agents in fixed order with full observability:
    1. DecomposerAgent - breaks query into sub-tasks
    2. RetrieverAgent - performs 2-hop retrieval
    3. CriticAgent - analyzes outputs for contradictions
    4. SynthesizerAgent - synthesizes final answer

    Guarantees:
    - Deterministic execution order
    - Observable state transitions
    - Full traceability via logging
    - Structured persistence integration
    - Failure isolation and recovery
    """

    # Fixed agent sequence
    AGENT_SEQUENCE = ["decomposer", "retriever", "critic", "synthesizer"]

    def __init__(
        self,
        budget_manager: Optional[BudgetManager] = None,
        exec_logger: Optional[ExecutionLogger] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """Initialize pipeline runner.

        Args:
            budget_manager: Optional BudgetManager (creates default if None).
            exec_logger: Optional ExecutionLogger (creates default if None).
            retry_config: Optional RetryConfig for retry behavior.
        """
        self.budget_manager = budget_manager or BudgetManager()
        self.exec_logger = exec_logger or ExecutionLogger()
        self.retry_config = retry_config or RetryConfig(max_retries=2)
        self._logger = get_logger("pipeline_runner")
        self._routing_decisions: list[dict[str, object]] = []
        self._retrieval_trace: dict[str, object] = {}
        self._event_sink: Optional[Callable[[dict[str, object]], Awaitable[None] | None]] = None

    async def _emit(self, event: dict[str, object]) -> None:
        if not self._event_sink:
            return
        result = self._event_sink(event)
        if hasattr(result, "__await__"):
            await result

    def _record_decision(
        self,
        decision_type: str,
        trigger_reason: str,
        selected_action: str,
        rejected_actions: list[str] | None = None,
        confidence: float = 1.0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        decision = {
            "decision_type": decision_type,
            "trigger_reason": trigger_reason,
            "confidence": confidence,
            "selected_action": selected_action,
            "rejected_actions": rejected_actions or [],
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._routing_decisions.append(decision)
        return decision

    def _query_is_self_contained(self, original_query: str, decomposer_flags: list[str]) -> bool:
        text = original_query.lower().strip()
        low_risk_markers = ("what is", "define", "describe", "explain", "list")
        if decomposer_flags:
            return False
        return any(text.startswith(marker) for marker in low_risk_markers) and len(text.split()) <= 6

    def _detect_adversarial_in_query(self, original_query: str) -> dict | None:
        lower = original_query.lower()
        indicators = []
        if "ignore previous" in lower or "ignore instructions" in lower:
            indicators.append("prompt_injection_ignore_instructions")
        if "click here" in lower or "<script>" in lower:
            indicators.append("html_injection")
        if any(word in lower for word in ("malicious", "attack", "exploit")):
            indicators.append("malicious_intent")
        if indicators:
            return {"indicators": indicators, "confidence": 0.9}
        return None

    def _contradiction_probability(self, original_query: str, decomposer_flags: list[str]) -> float:
        text = original_query.lower()
        score = 0.15
        if any(marker in text for marker in ("compare", "versus", "vs", "better", "worse", "why")):
            score += 0.35
        if any(marker in text for marker in ("or", "either", "neither")):
            score += 0.2
        if decomposer_flags:
            score += 0.1
        return min(1.0, score)

    def _should_skip_critic(self, original_query: str, decomposer_flags: list[str], retriever_output: Any | None) -> bool:
        if decomposer_flags:
            return False
        if retriever_output and retriever_output.metadata.get("conflicting_evidence"):
            return False
        return len(original_query.split()) <= 6 and not any(marker in original_query.lower() for marker in ("compare", "versus", "better", "worse", "contradict"))

    def _compress_context(self, context: SharedContext) -> None:
        if len(context.agent_outputs) > 4:
            context.agent_outputs = context.agent_outputs[-4:]
        if len(context.tool_call_log) > 6:
            context.tool_call_log = context.tool_call_log[-6:]

    async def run(
        self,
        original_query: str,
        event_sink: Optional[Callable[[dict[str, object]], Awaitable[None] | None]] = None,
    ) -> PipelineResult:
        """Execute the complete pipeline for a query.

        Args:
            original_query: The user's original query.

        Returns:
            PipelineResult with final answer, metrics, and traceability.
        """
        # Initialize execution
        job_id = str(uuid.uuid4())
        pipeline_start = time.perf_counter()
        start_time = datetime.utcnow()

        self._logger.info("starting pipeline for query: %s (job_id=%s)", original_query[:100], job_id)
        self._routing_decisions = []
        self._retrieval_trace = {}
        self._event_sink = event_sink
        await self._emit({"event_type": "orchestration_update", "job_id": job_id, "state": "started", "query": original_query})

        # Create shared context
        context = SharedContext(
            job_id=job_id,
            original_query=original_query,
        )

        # Initialize state manager
        state_manager = ExecutionStateManager(job_id)
        state_manager.initialize()
        state_manager.start_execution()
        state_manager.apply_to_context(context)

        # Initialize result assembler
        result_assembler = ResultAssembler(job_id)

        # Initialize retry coordinator
        retry_coordinator = RetryCoordinator(self.retry_config)

        # Execute agents sequentially
        try:
            await self._execute_decomposer(context, result_assembler)
            decomposer_output = next((item for item in context.agent_outputs if item.agent_id == "decomposer"), None)
            ambiguity_flags = context.sub_tasks[0].metadata.get("ambiguity_flags", []) if context.sub_tasks else []
            self_contained = self._query_is_self_contained(original_query, ambiguity_flags)
            contradiction_probability = self._contradiction_probability(original_query, ambiguity_flags)

            # Adversarial detection: simple deterministic heuristics
            adversarial = self._detect_adversarial_in_query(original_query)
            if adversarial:
                self._record_decision(
                    "adversarial_detected",
                    "heuristic match for injection/malicious indicators",
                    "mitigate_injection",
                    rejected_actions=["proceed_normally"],
                    confidence=adversarial.get("confidence", 0.9),
                    metadata={"indicators": adversarial.get("indicators")},
                )
                result_assembler.add_warning(f"Adversarial indicators detected: {adversarial.get('indicators')}")
                await self._emit({"event_type": "adversarial_detected", "indicators": adversarial.get("indicators")})

            if self_contained:
                self._record_decision(
                    "skip_agent",
                    "query is self-contained and low-risk",
                    "skip_retriever",
                    rejected_actions=["invoke_retriever"],
                    confidence=0.82,
                    metadata={"query": original_query},
                )
                await self._emit({"event_type": "routing_decision", "decision_type": "skip_agent", "selected_action": "skip_retriever", "trigger_reason": "query is self-contained and low-risk"})
            else:
                self._record_decision(
                    "invoke_agent",
                    "query requires external evidence",
                    "invoke_retriever",
                    rejected_actions=["skip_retriever"],
                    confidence=0.92,
                    metadata={"query": original_query},
                )
                await self._emit({"event_type": "routing_decision", "decision_type": "invoke_agent", "selected_action": "invoke_retriever", "trigger_reason": "query requires external evidence"})

            if not state_manager.can_continue():
                state_manager.mark_failed("decomposer failed")
                return self._finalize_result(context, state_manager, result_assembler, start_time, pipeline_start, success=False)

            retriever_output = None
            if not self_contained:
                retriever_output = await self._execute_retriever(context, result_assembler)
                if not state_manager.can_continue():
                    state_manager.mark_partial_failure("retriever failed or returned no results")

            skip_critic = self._should_skip_critic(original_query, ambiguity_flags, retriever_output)
            if contradiction_probability >= 0.65:
                reflection_tool = SelfReflectionTool()
                reflection_result = await reflection_tool.run({"job_id": job_id, "context": context.model_dump()}, timeout_seconds=3.0)
                self._record_decision(
                    "tool_fallback",
                    "contradiction probability exceeded threshold",
                    "invoke_self_reflection",
                    rejected_actions=["skip_self_reflection"],
                    confidence=contradiction_probability,
                    metadata={"reflection_success": reflection_result.success},
                )
                await self._emit({"event_type": "tool_call_completed", "tool": "self_reflection", "success": reflection_result.success})

            if skip_critic:
                self._record_decision(
                    "skip_agent",
                    "low-risk deterministic response",
                    "skip_critic",
                    rejected_actions=["invoke_critic"],
                    confidence=0.88,
                    metadata={"query": original_query},
                )
                await self._emit({"event_type": "routing_decision", "decision_type": "skip_agent", "selected_action": "skip_critic", "trigger_reason": "low-risk deterministic response"})
            else:
                self._record_decision(
                    "invoke_agent",
                    "query benefits from contradiction check",
                    "invoke_critic",
                    rejected_actions=["skip_critic"],
                    confidence=max(contradiction_probability, 0.6),
                    metadata={"query": original_query},
                )
                await self._emit({"event_type": "routing_decision", "decision_type": "invoke_agent", "selected_action": "invoke_critic", "trigger_reason": "query benefits from contradiction check"})
                await self._execute_critic(context, result_assembler)

            if len(context.agent_outputs) > 4 or len(context.tool_call_log) > 6:
                self._record_decision(
                    "context_compression",
                    "context budget exceeded threshold",
                    "compress_context",
                    rejected_actions=["keep_full_context"],
                    confidence=0.95,
                    metadata={"agent_outputs": len(context.agent_outputs), "tool_calls": len(context.tool_call_log)},
                )
                await self._emit({"event_type": "routing_decision", "decision_type": "context_compression", "selected_action": "compress_context", "trigger_reason": "context budget exceeded threshold"})
                self._compress_context(context)

            await self._execute_synthesizer(context, result_assembler)
            if not state_manager.can_continue():
                # Synthesizer failure marks final failure
                state_manager.mark_failed("synthesizer failed")
                return self._finalize_result(
                    context, state_manager, result_assembler, start_time, pipeline_start, success=False
                )

            # Successful completion
            state_manager.mark_succeeded()
            return self._finalize_result(context, state_manager, result_assembler, start_time, pipeline_start, success=True)

        except Exception as e:
            self._logger.error("unexpected error in pipeline: %s", str(e), exc_info=True)
            state_manager.mark_failed(f"unexpected error: {str(e)}")
            result_assembler.add_error(f"Pipeline error: {str(e)}")
            return self._finalize_result(context, state_manager, result_assembler, start_time, pipeline_start, success=False)

    def _attach_runtime_trace(self, result: PipelineResult, context: SharedContext) -> None:
        result.execution_trace.setdefault("routing_decisions", self._routing_decisions)
        result.execution_trace.setdefault("routing_summary", {
            "execution_path": [d["selected_action"] for d in self._routing_decisions],
            "skipped_agents": [d["selected_action"] for d in self._routing_decisions if d["selected_action"].startswith("skip_")],
            "fallback_paths": [d for d in self._routing_decisions if d["decision_type"] == "tool_fallback"],
        })
        result.execution_trace.setdefault("retrieval_trace", self._retrieval_trace)

    async def _execute_decomposer(self, context: SharedContext, result_assembler: ResultAssembler) -> bool:
        """Execute DecomposerAgent.

        Args:
            context: SharedContext to populate.
            result_assembler: Result collector.

        Returns:
            True if successful.
        """
        agent_start = time.perf_counter()
        agent_id = "decomposer"

        try:
            self._logger.info("executing %s", agent_id)

            config = AgentConfig(agent_id=agent_id, max_tokens=500)
            agent = DecomposerAgent(config, self.budget_manager, self.exec_logger)

            decompose_result = await agent.run(context)

            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=latency_ms,
                retries=0,
                token_count=0,
            )
            result_assembler.record_agent_event(event)

            # Add to agent outputs
            context.agent_outputs.append(
                AgentOutput(
                    agent_id=agent_id,
                    output_text=decompose_result.reasoning,
                    tokens_used=0,
                    metadata={"sub_task_count": len(decompose_result.sub_task_ids)},
                )
            )

            self._logger.info("decomposer complete: %d sub-tasks", len(decompose_result.sub_task_ids))
            return True

        except Exception as e:
            self._logger.error("decomposer failed: %s", str(e))
            result_assembler.add_error(f"Decomposer error: {str(e)}")
            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )
            result_assembler.record_agent_event(event)
            return False

    async def _execute_retriever(self, context: SharedContext, result_assembler: ResultAssembler):
        """Execute RetrieverAgent.

        Args:
            context: SharedContext with sub-tasks.
            result_assembler: Result collector.

        Returns:
            True if successful (or partially successful with results).
        """
        agent_start = time.perf_counter()
        agent_id = "retriever"

        try:
            self._logger.info("executing %s", agent_id)

            config = AgentConfig(agent_id=agent_id, max_tokens=5000)
            agent = RetrieverAgent(config, self.budget_manager, self.exec_logger)

            retrieve_result = await agent.run(context)

            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=latency_ms,
                retries=0,
                token_count=0,
            )
            result_assembler.record_agent_event(event)

            # Add to agent outputs
            context.agent_outputs.append(
                AgentOutput(
                    agent_id=agent_id,
                    output_text=retrieve_result.reasoning,
                    tokens_used=0,
                    metadata={
                        "results_count": len(retrieve_result.results),
                        "sources": len(retrieve_result.provenance_records),
                        "hops": retrieve_result.total_hops_performed,
                    },
                )
            )

            # Merge provenance
            for source_id, prov_record in retrieve_result.provenance_records.items():
                context.provenance_map[source_id] = prov_record

            hop1 = [r.model_dump() for r in retrieve_result.results if r.hop_number == 1]
            hop2 = [r.model_dump() for r in retrieve_result.results if r.hop_number == 2]
            self._retrieval_trace = {
                "first_hop_queries": retrieve_result.metadata.get("first_hop_queries", []),
                "second_hop_queries": retrieve_result.metadata.get("second_hop_queries", []),
                "first_hop_chunks": hop1,
                "second_hop_chunks": hop2,
                "chain_linkage": [
                    {"hop": 1, "query": q, "result_count": len(hop1)}
                    for q in retrieve_result.metadata.get("first_hop_queries", [])
                ] + [
                    {"hop": 2, "query": q, "result_count": len(hop2)}
                    for q in retrieve_result.metadata.get("second_hop_queries", [])
                ],
                "weaknesses": {
                    "redundant_chunks": retrieve_result.metadata.get("redundant_chunks", 0),
                    "insufficient_evidence": retrieve_result.metadata.get("insufficient_evidence", False),
                    "conflicting_evidence": retrieve_result.metadata.get("conflicting_evidence", False),
                },
            }

            self._logger.info("retriever complete: %d results from %d sources", len(retrieve_result.results), len(retrieve_result.provenance_records))
            return retrieve_result

        except Exception as e:
            self._logger.error("retriever failed: %s", str(e))
            result_assembler.add_warning(f"Retriever error (continuing): {str(e)}")
            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )
            result_assembler.record_agent_event(event)
            # Return True to allow pipeline to continue (retrieval is not fatal)
            return None

    async def _execute_critic(self, context: SharedContext, result_assembler: ResultAssembler) -> bool:
        """Execute CriticAgent.

        Args:
            context: SharedContext with agent outputs.
            result_assembler: Result collector.

        Returns:
            True if successful.
        """
        agent_start = time.perf_counter()
        agent_id = "critic"

        try:
            self._logger.info("executing %s", agent_id)

            config = AgentConfig(agent_id=agent_id, max_tokens=1000)
            agent = CriticAgent(config, self.budget_manager, self.exec_logger)

            critique_result = await agent.run(context)

            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=latency_ms,
                retries=0,
                token_count=0,
            )
            result_assembler.record_agent_event(event)

            # Add to agent outputs
            context.agent_outputs.append(
                AgentOutput(
                    agent_id=agent_id,
                    output_text=critique_result.reasoning,
                    tokens_used=0,
                    metadata={
                        "critiques_count": len(critique_result.critiques),
                        "flagged_count": len(critique_result.flagged_claims),
                        "contradictions": critique_result.contradictions_found,
                    },
                )
            )

            self._logger.info("critic complete: %d critiques, %d flagged", len(critique_result.critiques), len(critique_result.flagged_claims))
            return True

        except Exception as e:
            self._logger.error("critic failed: %s", str(e))
            result_assembler.add_warning(f"Critic error (continuing): {str(e)}")
            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )
            result_assembler.record_agent_event(event)
            return True

    async def _execute_synthesizer(self, context: SharedContext, result_assembler: ResultAssembler) -> bool:
        """Execute SynthesizerAgent.

        Args:
            context: SharedContext with all prior outputs.
            result_assembler: Result collector.

        Returns:
            True if successful.
        """
        agent_start = time.perf_counter()
        agent_id = "synthesizer"

        try:
            self._logger.info("executing %s", agent_id)

            config = AgentConfig(agent_id=agent_id, max_tokens=2000)
            agent = SynthesizerAgent(config, self.budget_manager, self.exec_logger)

            synthesis_result = await agent.run(context)

            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=latency_ms,
                retries=0,
                token_count=0,
            )
            result_assembler.record_agent_event(event)

            # Set final answer in context
            context.final_answer = synthesis_result.final_answer

            # Add to agent outputs
            context.agent_outputs.append(
                AgentOutput(
                    agent_id=agent_id,
                    output_text=synthesis_result.final_answer,
                    tokens_used=0,
                    metadata={
                        "confidence": synthesis_result.confidence_score.score,
                        "sources_used": synthesis_result.sources_used,
                        "claims_removed": len(synthesis_result.removed_claims),
                    },
                )
            )

            self._logger.info("synthesizer complete: confidence=%.2f", synthesis_result.confidence_score.score)
            return True

        except Exception as e:
            self._logger.error("synthesizer failed: %s", str(e))
            result_assembler.add_error(f"Synthesizer error: {str(e)}")
            latency_ms = (time.perf_counter() - agent_start) * 1000.0
            event = AgentExecutionEvent(
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )
            result_assembler.record_agent_event(event)
            return False

    def _finalize_result(
        self,
        context: SharedContext,
        state_manager: ExecutionStateManager,
        result_assembler: ResultAssembler,
        start_time: datetime,
        pipeline_start: float,
        success: bool,
    ) -> PipelineResult:
        """Finalize execution and build result.

        Args:
            context: Completed SharedContext.
            state_manager: State manager with transitions.
            result_assembler: Result collector.
            start_time: Pipeline start timestamp.
            pipeline_start: Pipeline start time (perf_counter).
            success: Whether execution was fully successful.

        Returns:
            Final PipelineResult.
        """
        end_time = datetime.utcnow()
        pipeline_duration_ms = (time.perf_counter() - pipeline_start) * 1000.0

        # Apply final state to context
        state_manager.apply_to_context(context)

        # Assemble final result
        result = result_assembler.assemble(context, success, pipeline_duration_ms, start_time, end_time)
        self._attach_runtime_trace(result, context)
        result.summary.metadata.setdefault("routing_decisions", self._routing_decisions)
        result.summary.metadata.setdefault("skipped_agents", [d["selected_action"] for d in self._routing_decisions if d["selected_action"].startswith("skip_")])
        result.summary.metadata.setdefault("fallback_paths", [d for d in self._routing_decisions if d["decision_type"] == "tool_fallback"])

        self._logger.info(
            "pipeline complete: success=%s, duration=%.0fms, agents=%d",
            success,
            pipeline_duration_ms,
            len(context.agent_outputs),
        )

        return result
