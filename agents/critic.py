"""CriticAgent implementation.

Deterministic rule-based critique of prior agent outputs.
Detects contradictions, flags low-confidence claims, and produces
structured critique records.
"""

from __future__ import annotations

from typing import Any, Dict

from shared.agent_base import BaseAgent
from context.shared_context import SharedContext
from agents.schemas import CritiqueOutput, CritiqueRecord, ConfidenceScore
from agents.contradiction_rules import KEYWORD_CONTRADICTIONS, detect_contradiction


class CriticAgent(BaseAgent):
    """Performs deterministic rule-based critique of agent outputs.

    Strategy:
    1. Inspect all agent outputs in SharedContext
    2. Check for internal contradictions (same agent producing conflicting claims)
    3. Check for cross-agent contradictions (different agents disagreeing)
    4. Assess confidence of claims based on evidence and consensus
    5. Flag low-confidence or contradictory claims for removal
    6. Produce structured CritiqueOutput

    Contradiction detection runs three deterministic, independently
    testable rule tiers (see agents/contradiction_rules.py): fixed
    antonym-pair keywords, numeric-claim divergence (e.g. "accuracy is
    76%" vs "82%"), and negation-aware shared-keyword matching. Each
    detector returns structured evidence so every flagged contradiction
    carries a human-readable justification — this stays fully explainable
    without needing an LLM judge.
    """

    # Kept for backward compatibility with any external references;
    # canonical definition now lives in agents/contradiction_rules.py.
    CONTRADICTION_KEYWORDS = KEYWORD_CONTRADICTIONS

    # Confidence threshold below which claims are flagged
    LOW_CONFIDENCE_THRESHOLD = 0.5

    async def run(self, shared_context: SharedContext) -> CritiqueOutput:
        """Critique agent outputs in the shared context.

        Args:
            shared_context: Contains agent_outputs to critique

        Returns:
            CritiqueOutput with critiques, flagged_claims, summary stats
        """
        self._logger.info("starting critique of %d agent outputs", len(shared_context.agent_outputs))

        critiques = []
        flagged_claims = []
        contradictions_found = 0
        low_confidence_count = 0

        # Collect all outputs for analysis
        outputs_by_agent = {}
        for output in shared_context.agent_outputs:
            if output.agent_id not in outputs_by_agent:
                outputs_by_agent[output.agent_id] = []
            outputs_by_agent[output.agent_id].append(output)

        # Phase 1: Check for same-agent contradictions
        for agent_id, outputs in outputs_by_agent.items():
            for i, output1 in enumerate(outputs):
                for output2 in outputs[i + 1 :]:
                    contradiction = self._detect_same_agent_contradiction(output1, output2)
                    if contradiction:
                        critiques.append(contradiction)
                        contradictions_found += 1
                        flagged_claims.append(output1.output_text or "")
                        flagged_claims.append(output2.output_text or "")
                        self._logger.debug(
                            "detected same-agent contradiction: %s vs %s", output1.output_text[:50], output2.output_text[:50]
                        )

        # Phase 2: Check for cross-agent contradictions
        all_outputs = shared_context.agent_outputs
        for i, output1 in enumerate(all_outputs):
            for output2 in all_outputs[i + 1 :]:
                if output1.agent_id != output2.agent_id:
                    contradiction = self._detect_cross_agent_contradiction(output1, output2)
                    if contradiction:
                        critiques.append(contradiction)
                        contradictions_found += 1
                        flagged_claims.append(output1.output_text or "")
                        self._logger.debug(
                            "detected cross-agent contradiction: %s vs %s", output1.agent_id, output2.agent_id
                        )

        # Phase 3: Assess confidence of all outputs
        for output in shared_context.agent_outputs:
            confidence_score = self._assess_confidence(output, shared_context)

            if confidence_score.score < self.LOW_CONFIDENCE_THRESHOLD:
                low_confidence_count += 1
                critique = CritiqueRecord(
                    agent_id=output.agent_id,
                    claim_or_output=output.output_text or "<<empty>>",
                    critique_type="low_confidence",
                    severity=1.0 - confidence_score.score,  # Higher severity for lower confidence
                    confidence=confidence_score,
                    details=f"Output confidence ({confidence_score.score:.2f}) below threshold ({self.LOW_CONFIDENCE_THRESHOLD})",
                    flagged=True,
                )
                critiques.append(critique)
                flagged_claims.append(output.output_text or "")
                self._logger.debug("flagged low-confidence output from %s", output.agent_id)

        # Deduplicate flagged claims
        flagged_claims = list(set(flagged_claims))

        # Compute overall quality score
        total_outputs = len(shared_context.agent_outputs)
        if total_outputs > 0:
            quality_ratio = 1.0 - (len(critiques) / (total_outputs * 2))  # Normalize by max possible critiques
            quality_ratio = max(0.0, min(1.0, quality_ratio))
        else:
            quality_ratio = 0.5

        overall_confidence = ConfidenceScore(
            score=quality_ratio,
            sources=list(outputs_by_agent.keys()),
            reasoning=f"Based on {len(critiques)} critiques across {total_outputs} outputs, "
            f"{contradictions_found} contradictions, {low_confidence_count} low-confidence claims.",
        )

        output = CritiqueOutput(
            critiques=critiques,
            flagged_claims=flagged_claims,
            contradictions_found=contradictions_found,
            low_confidence_count=low_confidence_count,
            overall_confidence=overall_confidence,
            reasoning="Performed deterministic rule-based critique on all agent outputs.",
        )

        self.exec_logger.log_event(
            agent_id=self.agent_id,
            event_type="critique_complete",
            token_count=0,
            job_id=shared_context.job_id,
            extra={
                "critiques_count": len(critiques),
                "flagged_count": len(flagged_claims),
                "contradictions": contradictions_found,
                "low_confidence": low_confidence_count,
            },
        )

        self._logger.info("critique complete: %d critiques, %d flagged claims", len(critiques), len(flagged_claims))

        return output

    def _evidence_to_details(self, evidence: Dict[str, object], label_a: str, label_b: str) -> str:
        """Render a rule-tier evidence dict into a human-readable justification."""
        rule = evidence.get("rule")
        if rule == "keyword_pair":
            return f"{label_a} says '{evidence['keyword_a']}' but {label_b} says '{evidence['keyword_b']}'"
        if rule == "numeric_divergence":
            return (
                f"Conflicting numeric claims about '{evidence['subject']}': "
                f"{label_a} states {evidence['value_a']:g}%, {label_b} states {evidence['value_b']:g}% "
                f"(divergence {evidence['divergence']:g} points)"
            )
        if rule == "negation":
            return f"'{evidence['keyword']}' is asserted in one output and negated in the other"
        return "Contradiction detected"

    def _detect_same_agent_contradiction(self, output1: Any, output2: Any) -> CritiqueRecord | None:
        """Detect contradiction between two outputs from the same agent.

        Runs the deterministic rule tiers in agents/contradiction_rules.py
        (keyword-pair, numeric-divergence, negation-aware).

        Returns:
            CritiqueRecord if contradiction found, else None.
        """
        text1 = output1.output_text or ""
        text2 = output2.output_text or ""

        evidence = detect_contradiction(text1, text2)
        if not evidence:
            return None

        return CritiqueRecord(
            agent_id=output1.agent_id,
            claim_or_output=output1.output_text or "<<empty>>",
            critique_type="contradiction",
            severity=0.8,
            confidence=ConfidenceScore(
                score=0.9,
                reasoning=f"Detected via rule '{evidence.get('rule')}'",
            ),
            details=self._evidence_to_details(evidence, output1.agent_id, output2.agent_id),
            related_claims=[output2.output_text or ""],
            flagged=True,
        )

    def _detect_cross_agent_contradiction(self, output1: Any, output2: Any) -> CritiqueRecord | None:
        """Detect contradiction between outputs from different agents.

        Runs the same deterministic rule tiers as same-agent detection,
        applied across agent boundaries.

        Returns:
            CritiqueRecord if contradiction found, else None.
        """
        text1 = output1.output_text or ""
        text2 = output2.output_text or ""

        evidence = detect_contradiction(text1, text2)
        if not evidence:
            return None

        return CritiqueRecord(
            agent_id=output1.agent_id,
            claim_or_output=output1.output_text or "<<empty>>",
            critique_type="contradiction",
            severity=0.7,
            confidence=ConfidenceScore(
                score=0.8,
                reasoning=f"Cross-agent disagreement via rule '{evidence.get('rule')}'",
            ),
            details=self._evidence_to_details(evidence, output1.agent_id, output2.agent_id),
            related_claims=[output2.output_text or ""],
            flagged=True,
        )

    def _assess_confidence(self, output: Any, shared_context: SharedContext) -> ConfidenceScore:
        """Assess the confidence of an output based on evidence signals.

        Heuristics:
        - More tool calls = higher confidence
        - Longer, more detailed outputs = higher confidence
        - Consensus with other agents = higher confidence
        - Low token count = slightly lower confidence

        Returns:
            ConfidenceScore for the output.
        """
        score = 0.5  # Base confidence

        # Signal 1: Tool call depth (more calls = more research)
        tool_calls = len(output.tool_calls)
        if tool_calls > 0:
            score += min(0.2, tool_calls * 0.05)  # Cap boost at +0.2

        # Signal 2: Output length (more detail = higher confidence)
        output_length = len(output.output_text or "")
        if output_length > 100:
            score += 0.15
        elif output_length > 50:
            score += 0.05

        # Signal 3: Token count (more work = higher confidence, but not overly)
        tokens = output.tokens_used
        if tokens > 100:
            score += 0.1
        elif tokens < 10:
            score -= 0.1

        # Signal 4: Check for metadata indicators
        if output.metadata.get("verified"):
            score += 0.2
        if output.metadata.get("incomplete"):
            score -= 0.2

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        reasoning = f"Based on {tool_calls} tool calls, {output_length} chars output, {tokens} tokens"

        return ConfidenceScore(
            score=score,
            sources=[output.agent_id],
            reasoning=reasoning,
        )
