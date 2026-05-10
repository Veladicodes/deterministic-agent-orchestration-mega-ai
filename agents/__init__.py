"""Agent layer implementations.

Clean, production-style agents that follow the BaseAgent contract.
Each agent is deterministic, observable, and persistence-aware.
"""

from agents.decomposer import DecomposerAgent
from agents.retriever import RetrieverAgent
from agents.critic import CriticAgent
from agents.synthesizer import SynthesizerAgent
from agents.schemas import (
    DecomposerOutput,
    RetrievalResult,
    RetrieverOutput,
    ConfidenceScore,
    CritiqueRecord,
    CritiqueOutput,
    SynthesisOutput,
)

__all__ = [
    # Agents
    "DecomposerAgent",
    "RetrieverAgent",
    "CriticAgent",
    "SynthesizerAgent",
    # Schemas
    "DecomposerOutput",
    "RetrievalResult",
    "RetrieverOutput",
    "ConfidenceScore",
    "CritiqueRecord",
    "CritiqueOutput",
    "SynthesisOutput",
]
