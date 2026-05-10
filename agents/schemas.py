"""Typed schemas for agent layer outputs.

These models provide structured contracts for agent communication,
enabling deterministic behavior, serialization, and persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from context.shared_context import ProvenanceRecord


class DecomposerOutput(BaseModel):
    """Output from the DecomposerAgent.

    Represents the breakdown of the original query into sub-tasks with
    dependency information and ambiguity signals.
    """

    sub_task_ids: List[str] = Field(default_factory=list)
    """Ordered list of sub-task IDs created in SharedContext."""

    dependency_graph: Dict[str, List[str]] = Field(default_factory=dict)
    """Maps task_id -> list of task_ids it depends on."""

    ambiguity_flags: List[str] = Field(default_factory=list)
    """Human-readable signals for unclear parts of the original query."""

    reasoning: str = ""
    """Concise explanation of decomposition strategy."""

    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievalResult(BaseModel):
    """Single retrieval result from the RetrieverAgent.

    Associates a claim/snippet with source provenance and hop depth.
    """

    query: str
    """The search query used to find this result."""

    source_url: str
    """URL or identifier of the source."""

    snippet: str
    """Retrieved text snippet."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """Confidence score [0, 1] for result relevance."""

    hop_number: int = 1
    """Retrieval hop depth (1=first-pass, 2=refined search, etc)."""

    source_title: Optional[str] = None
    """Optional source title or headline."""

    metadata: Dict[str, object] = Field(default_factory=dict)


class RetrieverOutput(BaseModel):
    """Output from the RetrieverAgent.

    Contains provenance-linked retrieval results and refinement strategy.
    """

    results: List[RetrievalResult] = Field(default_factory=list)
    """All retrieved results across hops."""

    provenance_records: Dict[str, ProvenanceRecord] = Field(default_factory=dict)
    """Maps source_id -> ProvenanceRecord for traceability."""

    refinement_queries: List[str] = Field(default_factory=list)
    """Search queries used across hops (in order)."""

    total_hops_performed: int = 1
    """Number of retrieval hops executed."""

    reasoning: str = ""
    """Explanation of retrieval strategy."""

    metadata: Dict[str, object] = Field(default_factory=dict)
    """Diagnostic metadata: hop confidences, redundancy, conflicts, etc."""

    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConfidenceScore(BaseModel):
    """Confidence assessment for a claim.

    Combines multiple signals into a single [0, 1] score with reasoning.
    """

    score: float = Field(default=0.5, ge=0.0, le=1.0)
    """Overall confidence [0, 1]."""

    sources: List[str] = Field(default_factory=list)
    """Source references supporting this score."""

    reasoning: str = ""
    """Explanation of how score was derived."""


class CritiqueRecord(BaseModel):
    """Single critique finding from the CriticAgent.

    Identifies a potential issue with agent outputs for upstream handling.
    """

    agent_id: str
    """Agent whose output is being critiqued."""

    claim_or_output: str
    """The specific claim or output being critiqued."""

    critique_type: str
    """Type: 'contradiction', 'low_confidence', 'incomplete', 'unclear'."""

    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    """Severity [0, 1]; 0 = minor style, 1 = fundamental blocker."""

    confidence: ConfidenceScore = Field(default_factory=lambda: ConfidenceScore())
    """Confidence in the critique itself."""

    details: str = ""
    """Detailed explanation of the critique."""

    related_claims: List[str] = Field(default_factory=list)
    """Other claims involved in contradiction (if applicable)."""

    flagged: bool = False
    """Whether this should cause the claim to be removed downstream."""

    created_at: datetime = Field(default_factory=datetime.utcnow)


class CritiqueOutput(BaseModel):
    """Output from the CriticAgent.

    Comprehensive critique analysis of prior agent outputs.
    """

    critiques: List[CritiqueRecord] = Field(default_factory=list)
    """All critique findings."""

    flagged_claims: List[str] = Field(default_factory=list)
    """Claims explicitly flagged for removal."""

    contradictions_found: int = 0
    """Count of contradictions detected."""

    low_confidence_count: int = 0
    """Count of low-confidence claims."""

    overall_confidence: ConfidenceScore = Field(
        default_factory=lambda: ConfidenceScore(score=0.5, reasoning="Not yet analyzed")
    )
    """Overall quality assessment of prior outputs."""

    reasoning: str = ""
    """Summary of critique strategy."""

    created_at: datetime = Field(default_factory=datetime.utcnow)


class SynthesisOutput(BaseModel):
    """Output from the SynthesizerAgent.

    Final consolidated answer with provenance and traceability.
    """

    final_answer: str
    """The consolidated answer."""

    provenance_links: Dict[str, ProvenanceRecord] = Field(default_factory=dict)
    """Source provenance for claims in final_answer."""

    removed_claims: List[str] = Field(default_factory=list)
    """Claims that were filtered out due to critique or low confidence."""

    confidence_score: ConfidenceScore = Field(
        default_factory=lambda: ConfidenceScore(score=0.7, reasoning="Default synthesis confidence")
    )
    """Confidence in the final answer."""

    reasoning: str = ""
    """Explanation of synthesis decisions."""

    sources_used: int = 0
    """Count of unique sources used in final answer."""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "extra": "forbid",
    }
