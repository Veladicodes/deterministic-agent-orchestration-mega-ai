"""ResultAssembler implementation.

Collects and formats orchestration results into structured output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from shared.enums import ExecutionStatus
from shared.logging import get_logger
from context.shared_context import SharedContext
from orchestration.schemas import PipelineResult, ExecutionSummary, AgentExecutionEvent


class ResultAssembler:
    """Assembles final pipeline result from execution artifacts.

    Collects:
    - Agent outputs
    - Provenance maps
    - Execution metrics
    - Tool call metrics
    - Error/warning information

    Produces deterministic, structured PipelineResult for consumption
    by API layer or external callers.
    """

    def __init__(self, job_id: str):
        """Initialize result assembler.

        Args:
            job_id: Job identifier for logging.
        """
        self.job_id = job_id
        self._logger = get_logger(f"result_assembler.{job_id}")
        self._agent_events: dict[str, AgentExecutionEvent] = {}
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def record_agent_event(self, event: AgentExecutionEvent) -> None:
        """Record execution event for an agent.

        Args:
            event: AgentExecutionEvent to record.
        """
        self._agent_events[event.agent_id] = event
        self._logger.debug("recorded event for agent %s", event.agent_id)

    def add_error(self, message: str) -> None:
        """Add an error message.

        Args:
            message: Error description.
        """
        self._errors.append(message)
        self._logger.warning("added error: %s", message)

    def add_warning(self, message: str) -> None:
        """Add a warning message.

        Args:
            message: Warning description.
        """
        self._warnings.append(message)
        self._logger.debug("added warning: %s", message)

    def assemble(
        self,
        context: SharedContext,
        success: bool,
        pipeline_duration_ms: float,
        start_time: datetime,
        end_time: datetime,
    ) -> PipelineResult:
        """Assemble final result from execution artifacts.

        Args:
            context: SharedContext with execution results.
            success: Whether execution was fully successful.
            pipeline_duration_ms: Total execution time in milliseconds.
            start_time: Pipeline start timestamp.
            end_time: Pipeline end timestamp.

        Returns:
            Structured PipelineResult ready for serialization.
        """
        # Build execution summary
        summary = self._build_summary(
            context,
            success,
            pipeline_duration_ms,
            start_time,
            end_time,
        )

        # Collect agent outputs
        agent_outputs = self._collect_agent_outputs(context)

        # Build execution trace
        execution_trace = self._build_execution_trace(context)

        # Extract final answer and provenance
        final_answer = context.final_answer
        provenance_links = dict(context.provenance_map) if context.provenance_map else {}

        # Build final result
        result = PipelineResult(
            success=success,
            summary=summary,
            final_answer=final_answer,
            execution_trace=execution_trace,
            provenance_links=provenance_links,
            agent_outputs=agent_outputs,
            errors=self._errors,
            warnings=self._warnings,
            timestamp=datetime.utcnow(),
        )

        self._logger.info(
            "assembled result: success=%s, agents=%d, errors=%d, warnings=%d",
            success,
            len(agent_outputs),
            len(self._errors),
            len(self._warnings),
        )

        return result

    def _build_summary(
        self,
        context: SharedContext,
        success: bool,
        pipeline_duration_ms: float,
        start_time: datetime,
        end_time: datetime,
    ) -> ExecutionSummary:
        """Build execution summary from context and metrics.

        Args:
            context: SharedContext with execution data.
            success: Whether fully successful.
            pipeline_duration_ms: Total execution time.
            start_time: Start timestamp.
            end_time: End timestamp.

        Returns:
            ExecutionSummary with all metrics.
        """
        # Count agent outcomes
        agents_succeeded = 0
        agents_failed = 0
        agents_skipped = 0

        for task in context.sub_tasks:
            if task.status.value == "SUCCEEDED":
                agents_succeeded += 1
            elif task.status.value == "FAILED":
                agents_failed += 1
            elif task.status.value == "PENDING":
                agents_skipped += 1

        # Aggregate tool calls and tokens
        total_tool_calls = len(context.tool_call_log)
        total_tokens = sum(context.token_budget_usage.values())

        # Determine final status
        if success:
            final_status = ExecutionStatus.SUCCEEDED
        elif agents_succeeded > 0 and agents_failed > 0:
            final_status = ExecutionStatus.PARTIAL_FAILURE
        else:
            final_status = ExecutionStatus.FAILED

        summary = ExecutionSummary(
            job_id=self.job_id,
            status=final_status,
            total_agents=len(context.sub_tasks),
            agents_succeeded=agents_succeeded,
            agents_failed=agents_failed,
            agents_skipped=agents_skipped,
            total_retries=sum(e.retries for e in self._agent_events.values()),
            total_tool_calls=total_tool_calls,
            total_tokens_used=total_tokens,
            pipeline_duration_ms=pipeline_duration_ms,
            started_at=start_time,
            completed_at=end_time,
            partial_failure=agents_succeeded > 0 and agents_failed > 0,
            final_answer=context.final_answer,
            metadata={
                "agent_events": len(self._agent_events),
                "execution_states": len(context.execution_state.errors),
            },
        )

        return summary

    def _collect_agent_outputs(self, context: SharedContext) -> dict[str, object]:
        """Collect outputs from all agents.

        Args:
            context: SharedContext with agent outputs.

        Returns:
            Dict mapping agent_id -> output object.
        """
        outputs = {}

        for output in context.agent_outputs:
            outputs[output.agent_id] = {
                "output_text": output.output_text,
                "tokens_used": output.tokens_used,
                "timestamp": output.timestamp.isoformat(),
                "tool_calls": len(output.tool_calls),
                "metadata": output.metadata,
            }

        return outputs

    def _build_execution_trace(self, context: SharedContext) -> dict[str, object]:
        """Build structured execution trace for debugging.

        Args:
            context: SharedContext with execution data.

        Returns:
            Dict with execution timeline and artifacts.
        """
        trace = {
            "job_id": context.job_id,
            "original_query": context.original_query,
            "agent_events": [
                {
                    "agent_id": event.agent_id,
                    "status": event.status.value if hasattr(event.status, "value") else str(event.status),
                    "latency_ms": event.latency_ms,
                    "retries": event.retries,
                    "token_count": event.token_count,
                    "tool_calls": event.tool_calls,
                    "timestamp": event.timestamp.isoformat(),
                    "error": event.error,
                }
                for event in self._agent_events.values()
            ],
            "sub_tasks": [
                {
                    "id": task.id,
                    "description": task.description,
                    "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                    "assigned_agent": task.assigned_agent,
                }
                for task in context.sub_tasks
            ],
            "tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "success": call.failure is None,
                    "latency_ms": call.latency_ms,
                    "retries": call.retries,
                }
                for call in context.tool_call_log
            ],
            "agents_executed": len(context.agent_outputs),
            "total_risk_flags": len(context.risk_flags),
        }

        # Build lightweight claim -> retrieval chunk contribution mapping
        claim_contributions = []
        final_answer = context.final_answer or ""
        if final_answer:
            # Sentence-split naively on periods for determinism
            sentences = [s.strip() for s in final_answer.split(".") if s.strip()]

            # Collect search hits from tool_call_log where available
            web_hits = []
            for call in context.tool_call_log:
                try:
                    if call.tool_name == "web_search" and call.output and isinstance(call.output, dict):
                        for res in call.output.get("results", []):
                            web_hits.append({
                                "url": res.get("url"),
                                "title": res.get("title"),
                                "snippet": res.get("snippet", ""),
                            })
                except Exception:
                    continue

            def _tokens(text: str) -> set[str]:
                return {t.lower() for t in re.findall(r"\w+", text)}

            import re

            for sent in sentences:
                s_tokens = _tokens(sent)
                contributors = []
                for hit in web_hits:
                    overlap = len(s_tokens.intersection(_tokens(hit.get("snippet", "") + " " + hit.get("title", ""))))
                    if overlap >= 3:
                        # Attempt to get hop info from context.provenance_map
                        hop = None
                        prov = context.provenance_map.get(hit.get("url")) if context.provenance_map else None
                        if prov and isinstance(prov, dict):
                            hop = prov.get("metadata", {}).get("hop")
                        contributors.append({"source": hit.get("url"), "overlap": overlap, "hop": hop})

                claim_contributions.append({"claim": sent, "contributors": contributors})

        trace["claim_contributions"] = claim_contributions

        return trace
