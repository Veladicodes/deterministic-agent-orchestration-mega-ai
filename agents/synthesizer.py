"""SynthesizerAgent implementation.

Combines outputs from all prior agents, removes flagged claims,
preserves provenance, and produces the final answer.
"""

from __future__ import annotations

from typing import Any

from shared.agent_base import BaseAgent
from context.shared_context import SharedContext, ProvenanceRecord
from agents.schemas import SynthesisOutput, ConfidenceScore, RetrieverOutput, CritiqueOutput


class SynthesizerAgent(BaseAgent):
    """Synthesizes outputs from all prior agents into final answer.

    Strategy:
    1. Collect outputs from DecomposerAgent, RetrieverAgent, CriticAgent
    2. Filter out flagged claims from CritiqueAgent
    3. Merge retrieval results with preserved provenance
    4. Build final answer by combining non-flagged outputs
    5. Compute overall confidence based on remaining evidence
    6. Return provenance-linked SynthesisOutput
    """

    async def run(self, shared_context: SharedContext) -> SynthesisOutput:
        """Synthesize final answer from all agent outputs.

        Args:
            shared_context: Contains all prior agent outputs and logs

        Returns:
            SynthesisOutput with final_answer, provenance, confidence
        """
        self._logger.info("synthesizing final answer from %d agent outputs", len(shared_context.agent_outputs))

        # Extract prior agent outputs
        retrieved_output = self._extract_output_by_agent_type(shared_context, "retriever")
        critique_output = self._extract_output_by_agent_type(shared_context, "critic")

        # Collect all outputs that aren't flagged
        flagged_claims = set()
        if critique_output and isinstance(critique_output, dict):
            flagged_claims = set(critique_output.get("flagged_claims", []))

        # Build claim pool from non-flagged sources
        claim_pool = self._build_claim_pool(shared_context, flagged_claims)

        # Extract provenance from retrieval output
        provenance_links = {}
        retrieved_results = []
        if retrieved_output:
            if isinstance(retrieved_output, dict):
                retrieved_results = retrieved_output.get("results", [])
                raw_prov = retrieved_output.get("provenance_records", {})
                for key, record in raw_prov.items():
                    if isinstance(record, dict):
                        provenance_links[key] = ProvenanceRecord(
                            source_id=record.get("source_id", key),
                            weight=record.get("weight", 1.0),
                            metadata=record.get("metadata", {}),
                        )

        # Build final answer by combining claims
        final_answer = self._synthesize_claims(claim_pool, retrieved_results)

        # Calculate confidence based on evidence
        sources_used = len(set(r.get("source_url", "") for r in retrieved_results)) if retrieved_results else 0
        confidence_score = self._compute_synthesis_confidence(claim_pool, sources_used, flagged_claims)

        removed_claims = list(flagged_claims)

        reasoning = (
            f"Synthesized from {len(claim_pool)} non-flagged claims, "
            f"{len(removed_claims)} flagged claims excluded, "
            f"{sources_used} unique sources, "
            f"overall confidence {confidence_score.score:.2f}"
        )

        output = SynthesisOutput(
            final_answer=final_answer,
            provenance_links=provenance_links,
            removed_claims=removed_claims,
            confidence_score=confidence_score,
            reasoning=reasoning,
            sources_used=sources_used,
        )

        self.exec_logger.log_event(
            agent_id=self.agent_id,
            event_type="synthesis_complete",
            token_count=0,
            job_id=shared_context.job_id,
            extra={
                "claims_used": len(claim_pool),
                "claims_removed": len(removed_claims),
                "sources": sources_used,
                "confidence": confidence_score.score,
            },
        )

        self._logger.info("synthesis complete: %d claims used, %d removed, confidence %.2f", len(claim_pool), len(removed_claims), confidence_score.score)

        return output

    def _extract_output_by_agent_type(self, shared_context: SharedContext, agent_type: str) -> Any:
        """Extract outputs from agents matching the given type.

        Looks for agent_id patterns like 'decomposer', 'retriever', 'critic'.

        Returns:
            First matching agent output dict/object, or None.
        """
        for output in shared_context.agent_outputs:
            if agent_type.lower() in output.agent_id.lower():
                # Try to return as dict for consistency
                if hasattr(output, "model_dump"):
                    return output.model_dump()
                elif hasattr(output, "dict"):
                    return output.dict()
                else:
                    return output

        return None

    def _build_claim_pool(self, shared_context: SharedContext, flagged_claims: set[str]) -> list[str]:
        """Extract all non-flagged claims from agent outputs.

        Returns:
            List of claim strings to consider for synthesis.
        """
        claims = []

        for output in shared_context.agent_outputs:
            if output.output_text and output.output_text not in flagged_claims:
                claims.append(output.output_text)

        # Also add provenance from retrieval results
        for record in shared_context.tool_call_log:
            if record.tool_name == "web_search" and record.output:
                results = record.output.get("results", [])
                for result in results:
                    snippet = result.get("snippet", "")
                    if snippet and snippet not in flagged_claims:
                        claims.append(snippet)

        return claims

    def _synthesize_claims(self, claim_pool: list[str], retrieved_results: list[dict]) -> str:
        """Combine claims into a coherent final answer.

        Simple strategy: concatenate claims with connecting phrases.

        Returns:
            Final answer string.
        """
        if not claim_pool and not retrieved_results:
            return "No information available to synthesize."

        answer_parts = []

        # Add top claims from pool
        for i, claim in enumerate(claim_pool[:3]):  # Limit to first 3 for readability
            if i == 0:
                answer_parts.append(claim)
            else:
                answer_parts.append(f"Additionally, {claim.lower()}")

        # Add retrieved snippets if available
        if retrieved_results:
            snippet = retrieved_results[0].get("snippet", "")
            if snippet and snippet not in answer_parts:
                answer_parts.append(f"Based on retrieval: {snippet[:200]}")

        return " ".join(answer_parts) if answer_parts else "Unable to synthesize a complete answer."

    def _compute_synthesis_confidence(self, claim_pool: list[str], sources_used: int, flagged_claims: set[str]) -> ConfidenceScore:
        """Compute overall confidence in the final answer.

        Factors:
        - Number of non-flagged claims
        - Number of unique sources
        - Ratio of claims kept vs removed

        Returns:
            ConfidenceScore for the synthesis.
        """
        base_confidence = 0.5

        # Signal 1: Claim pool size (more claims = higher confidence)
        if len(claim_pool) > 5:
            base_confidence += 0.25
        elif len(claim_pool) > 2:
            base_confidence += 0.15
        elif len(claim_pool) == 0:
            base_confidence = 0.2

        # Signal 2: Source diversity
        if sources_used > 3:
            base_confidence += 0.2
        elif sources_used > 1:
            base_confidence += 0.1

        # Signal 3: Claims removed (if many claims removed, lower confidence)
        if len(flagged_claims) > 0:
            removal_penalty = min(0.2, len(flagged_claims) * 0.05)
            base_confidence -= removal_penalty

        # Clamp to [0, 1]
        base_confidence = max(0.0, min(1.0, base_confidence))

        reasoning = (
            f"Synthesis confidence: {len(claim_pool)} claims used, "
            f"{sources_used} sources, {len(flagged_claims)} claims removed"
        )

        return ConfidenceScore(
            score=base_confidence,
            reasoning=reasoning,
        )
