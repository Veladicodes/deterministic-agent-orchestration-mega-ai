"""DecomposerAgent implementation.

Analyzes the original query, breaks it into structured sub-tasks with
dependencies, and identifies ambiguity indicators. Deterministic based on
query structure, not LLM reasoning.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

from shared.agent_base import BaseAgent
from shared.enums import ExecutionStatus
from context.shared_context import SharedContext, SubTask
from agents.schemas import DecomposerOutput


class DecomposerAgent(BaseAgent):
    """Decomposes queries into structured sub-tasks with dependency tracking.

    Strategy:
    1. Normalize and tokenize the query
    2. Detect intent patterns (find, analyze, compare, list, etc.)
    3. Extract entities and relationships
    4. Segment into logical sub-tasks
    5. Build dependency graph
    6. Flag ambiguous phrases
    """

    # Pattern matching for decomposition
    INTENT_PATTERNS = {
        "search": r"\b(find|search|look for|locate|discover)\b",
        "analyze": r"\b(analyze|examine|assess|evaluate|review)\b",
        "compare": r"\b(compare|contrast|difference|vs\.?|versus)\b",
        "list": r"\b(list|enumerate|show|display|get all)\b",
        "summarize": r"\b(summarize|sum up|overview|brief|synopsis)\b",
        "explain": r"\b(explain|clarify|describe|how|why)\b",
    }

    CONJUNCTION_PATTERNS = {
        "and": r"\band\b",
        "or": r"\bor\b",
        "then": r"\bthen\b",
    }

    AMBIGUITY_PATTERNS = {
        "vague_quantity": r"\b(some|many|few|several|multiple)\b",
        "relative_reference": r"\b(best|worst|most|least|top|bottom)\b",
        "time_ambiguity": r"\b(recently|soon|later|eventually)\b",
        "pronoun": r"\b(it|that|this|those|these)\b",
    }

    async def run(self, shared_context: SharedContext) -> DecomposerOutput:
        """Decompose the shared context's original query into sub-tasks.

        Args:
            shared_context: Execution context with original_query

        Returns:
            DecomposerOutput with sub_task_ids, dependency_graph, ambiguity_flags
        """
        query = shared_context.original_query
        self._logger.info("decomposing query: %s", query)

        # Step 1: Detect ambiguity early
        ambiguity_flags = self._detect_ambiguities(query)

        # Step 2: Segment query into logical units
        segments = self._segment_query(query)
        self._logger.debug("detected %d segments", len(segments))

        # Step 3: Create sub-tasks for each segment
        sub_task_ids = []
        dependency_graph: Dict[str, List[str]] = {}

        for i, segment in enumerate(segments):
            task_id = str(uuid.uuid4())
            sub_task_ids.append(task_id)

            # Extract intent and entities from segment
            intent = self._detect_intent(segment)
            entities = self._extract_entities(segment)

            description = f"[{intent}] {segment[:100]}"
            if len(segment) > 100:
                description += "..."

            # Create SubTask in shared context
            sub_task = SubTask(
                id=task_id,
                description=description,
                status=ExecutionStatus.PENDING,
                metadata={
                    "segment_index": i,
                    "intent": intent,
                    "entities": entities,
                },
            )
            shared_context.sub_tasks.append(sub_task)

        # Step 4: Build dependency graph
        # Simple heuristic: tasks depend on previous ones if connected by "then"
        # or if they reference relative terms like "best of" or "top"
        dependency_graph = self._build_dependency_graph(segments, sub_task_ids)

        # Step 5: Log execution
        reasoning = (
            f"Decomposed into {len(segments)} segments based on "
            f"conjunctions and intent patterns. "
            f"Detected {len(ambiguity_flags)} ambiguity signals."
        )

        output = DecomposerOutput(
            sub_task_ids=sub_task_ids,
            dependency_graph=dependency_graph,
            ambiguity_flags=ambiguity_flags,
            reasoning=reasoning,
        )

        self.exec_logger.log_event(
            agent_id=self.agent_id,
            event_type="decompose_complete",
            token_count=0,  # No tokens for deterministic analysis
            job_id=shared_context.job_id,
            extra={
                "segments_count": len(segments),
                "ambiguities_count": len(ambiguity_flags),
                "dependencies": len(dependency_graph),
            },
        )

        self._logger.info("decomposition complete: %d tasks, %d dependencies", len(sub_task_ids), len(dependency_graph))

        return output

    def _detect_ambiguities(self, query: str) -> List[str]:
        """Identify ambiguous language patterns in the query.

        Returns:
            List of ambiguity descriptions like "vague_quantity", "pronoun", etc.
        """
        ambiguities = []

        for ambiguity_type, pattern in self.AMBIGUITY_PATTERNS.items():
            if re.search(pattern, query, re.IGNORECASE):
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    ambiguities.append(f"{ambiguity_type}: '{match.group()}'")

        return ambiguities

    def _segment_query(self, query: str) -> List[str]:
        """Segment query by conjunctions and sentence boundaries.

        Returns:
            List of query segments (non-empty strings).
        """
        # Split on primary conjunctions first
        segments = re.split(r"\band\b", query, flags=re.IGNORECASE)

        # Further split segments on "or" and "then"
        refined = []
        for seg in segments:
            parts = re.split(r"\b(or|then)\b", seg, flags=re.IGNORECASE)
            # Re-split creates alternating text and conjunction, filter out conjunctions
            for part in parts:
                if part.strip() and not re.match(r"^(or|then)$", part, re.IGNORECASE):
                    refined.append(part.strip())

        # Filter out empty segments
        segments = [s for s in refined if s]

        # If no segments (single query), return as is
        if not segments:
            segments = [query.strip()]

        return segments

    def _detect_intent(self, segment: str) -> str:
        """Classify the segment's intent using pattern matching.

        Returns:
            Intent classification: 'search', 'analyze', 'compare', etc.
        """
        for intent_type, pattern in self.INTENT_PATTERNS.items():
            if re.search(pattern, segment, re.IGNORECASE):
                return intent_type

        # Default to 'search' if no specific intent detected
        return "search"

    def _extract_entities(self, segment: str) -> List[str]:
        """Extract potential entities from a segment.

        Simple heuristic: capitalized words, quoted strings, and nouns.

        Returns:
            List of identified entities.
        """
        entities = []

        # Capitalized words (proper nouns)
        capitalized = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", segment)
        entities.extend(capitalized)

        # Quoted strings
        quoted = re.findall(r'"([^"]+)"', segment)
        entities.extend(quoted)

        return list(set(entities))  # Remove duplicates

    def _build_dependency_graph(self, segments: List[str], task_ids: List[str]) -> Dict[str, List[str]]:
        """Build a dependency graph based on segment relationships.

        Simple heuristic:
        - Task i depends on task i-1 if connected by "then"
        - Task depends on earlier tasks if it uses relative terms

        Returns:
            Dict mapping task_id -> list of task_ids it depends on.
        """
        graph: Dict[str, List[str]] = {}

        for task_id in task_ids:
            graph[task_id] = []

        # Check for "then" relationships and relative comparisons
        for i, segment in enumerate(segments):
            if i > 0 and re.search(r"\bthen\b", segment, re.IGNORECASE):
                # Task depends on previous task
                graph[task_ids[i]].append(task_ids[i - 1])

            # Check for relative references (best, worst, top, etc.) that imply dependency
            if re.search(self.AMBIGUITY_PATTERNS["relative_reference"], segment, re.IGNORECASE):
                # Tentatively depend on earlier tasks
                for j in range(i):
                    if graph[task_ids[i]] is None:
                        graph[task_ids[i]] = []
                    if task_ids[j] not in graph[task_ids[i]]:
                        graph[task_ids[i]].append(task_ids[j])

        return graph
