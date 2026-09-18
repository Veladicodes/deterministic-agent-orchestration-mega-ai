"""LLMSynthesizerAgent implementation.

An opt-in variant of SynthesizerAgent that replaces the deterministic
string-concatenation synthesis strategy with a real LLM call, while
preserving the exact SynthesisOutput schema, provenance handling, and
confidence computation of the base class. The Decomposer, Retriever's
routing, Critic's filtering, and all orchestration/retry/replay logic
remain fully deterministic regardless of which synthesizer is selected;
only this prose-generation leaf becomes non-deterministic, and only when
explicitly opted into via `Settings.synthesizer_backend == "llm"`.
"""

from __future__ import annotations

from typing import Optional

from shared.tool_base import BaseTool
from context.shared_context import ToolCallRecord
from agents.synthesizer import SynthesizerAgent
from tools.llm_tool import LLMTool

_FALLBACK_NOTE = " (LLM synthesis unavailable; showing extracted claims instead.)"


class LLMSynthesizerAgent(SynthesizerAgent):
    """SynthesizerAgent variant that synthesizes prose via a real LLM call.

    If the LLM call fails for any reason (missing key, timeout, API
    error), this agent falls back to the parent class's deterministic
    string-concatenation synthesis rather than failing the pipeline —
    Synthesizer failures are a blocking (FAILED) condition at the
    orchestration layer, so a non-deterministic tool's transient failure
    must not be allowed to fail the whole run.
    """

    def __init__(self, *args, llm_tool: Optional[BaseTool] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._llm_tool = llm_tool or LLMTool(api_key=None)

    async def _synthesize_claims(self, claim_pool: list[str], retrieved_results: list[dict]) -> str:
        deterministic_answer = super()._synthesize_claims(claim_pool, retrieved_results)

        if not claim_pool and not retrieved_results:
            return deterministic_answer

        prompt = self._build_prompt(claim_pool, retrieved_results)
        payload = {"prompt": prompt, "job_id": self.agent_id, "max_tokens": 400}
        tool_result = await self.execute_tool(self._llm_tool, payload)

        # Record the call so LLM cost/tokens are visible in traces and
        # evaluation metrics exactly like search tool calls already are
        # (context/shared_context.py's ToolCallRecord, populated by
        # RetrieverAgent for web_search). `output` carries the raw
        # tokens/cost_usd payload from LLMTool with no schema change needed.
        context = getattr(self, "_current_context", None)
        if context is not None:
            context.tool_call_log.append(
                ToolCallRecord(
                    tool_name="llm_synthesis",
                    input={"prompt_length": len(prompt)},
                    output=tool_result.result,
                    failure=tool_result.failure_mode.value if not tool_result.success else None,
                    latency_ms=tool_result.latency_ms,
                )
            )

        if not tool_result.success or not tool_result.result or not tool_result.result.get("text"):
            self._logger.warning(
                "LLM synthesis failed (%s); falling back to deterministic synthesis",
                tool_result.error_message or tool_result.failure_mode.value,
            )
            return deterministic_answer + _FALLBACK_NOTE

        return tool_result.result["text"].strip()

    def _build_prompt(self, claim_pool: list[str], retrieved_results: list[dict]) -> str:
        claims_block = "\n".join(f"- {claim}" for claim in claim_pool[:8]) or "(no claims extracted)"
        snippets_block = "\n".join(
            f"- {r.get('snippet', '')}" for r in retrieved_results[:5] if r.get("snippet")
        ) or "(no retrieved snippets)"

        return (
            "You are the synthesis stage of a deterministic multi-agent pipeline. "
            "You are given a set of claims that have already survived contradiction "
            "and confidence filtering by an upstream critic. Write a concise, factual "
            "answer using only the information below. Do not invent facts, sources, or "
            "numbers that are not present in the claims or snippets.\n\n"
            f"Filtered claims:\n{claims_block}\n\n"
            f"Retrieved snippets:\n{snippets_block}\n\n"
            "Final answer:"
        )
