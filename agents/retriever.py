"""RetrieverAgent implementation.

Performs 2-hop web retrieval with query refinement between hops.
Returns provenance-linked results for downstream synthesis.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from shared.agent_base import BaseAgent
from shared.tool_base import RetryPolicy, ToolResult
from context.shared_context import SharedContext, ProvenanceRecord, ToolCallRecord
from tools.web_search import WebSearchTool
from agents.schemas import RetrieverOutput, RetrievalResult


class RetrieverAgent(BaseAgent):
    """Performs multi-hop retrieval with query refinement.

    Strategy:
    1. Extract initial search queries from sub-tasks
    2. Execute first-hop retrieval
    3. Analyze results and refine queries based on coverage gaps
    4. Execute second-hop retrieval with refined queries
    5. Combine results, build provenance map, return structured output
    """

    def __init__(self, *args, web_search_tool: WebSearchTool | None = None, **kwargs):
        """Initialize with optional WebSearchTool dependency injection for testing."""
        super().__init__(*args, **kwargs)
        self.web_search_tool = web_search_tool or WebSearchTool()

    async def run(self, shared_context: SharedContext) -> RetrieverOutput:
        """Execute multi-hop retrieval on sub-tasks.

        Args:
            shared_context: Execution context with sub_tasks

        Returns:
            RetrieverOutput with results, provenance, refinement queries
        """
        self._logger.info("starting retrieval for %d sub-tasks", len(shared_context.sub_tasks))

        all_results: list[RetrievalResult] = []
        all_queries: list[str] = []
        provenance_records: dict[str, ProvenanceRecord] = {}

        # Hop 1: Initial retrieval
        first_hop_queries = self._extract_initial_queries(shared_context.sub_tasks)
        all_queries.extend(first_hop_queries)

        hop1_results = await self._execute_retrieval_hop(
            first_hop_queries, hop_number=1, shared_context=shared_context
        )
        all_results.extend(hop1_results)

        self._logger.info("first hop returned %d results", len(hop1_results))

        # Hop 2: Refined retrieval only when first-hop evidence is weak.
        refined_queries = self._refine_queries(first_hop_queries, hop1_results)
        hop2_results: list[RetrievalResult] = []
        if refined_queries:
            all_queries.extend(refined_queries)
            hop2_results = await self._execute_retrieval_hop(
                refined_queries, hop_number=2, shared_context=shared_context
            )
            all_results.extend(hop2_results)
            self._logger.info("second hop returned %d results", len(hop2_results))
        else:
            self._logger.info("second hop skipped because first-hop evidence was sufficient")

        # Build provenance map
        for result in all_results:
            source_id = result.source_url
            if source_id not in provenance_records:
                provenance_records[source_id] = ProvenanceRecord(
                    source_id=source_id,
                    weight=result.confidence,
                    metadata={
                        "title": result.source_title or "Unknown",
                        "query": result.query,
                        "hop": result.hop_number,
                        "source_confidence": result.confidence,
                        "provenance_strength": min(1.0, result.confidence + 0.05 * result.hop_number),
                        "ambiguity_score": max(0.0, 1.0 - result.confidence),
                    },
                )

        hop1_confidence = sum(r.confidence for r in hop1_results) / max(len(hop1_results), 1)
        hop2_confidence = sum(r.confidence for r in hop2_results) / max(len(hop2_results), 1) if hop2_results else 0.0
        redundant_chunks = max(0, len(all_results) - len(provenance_records))
        insufficient_evidence = len(all_results) < 2 or hop1_confidence < 0.7
        conflicting_evidence = any("versus" in r.snippet.lower() or "contradict" in r.snippet.lower() for r in all_results)

        reasoning = (
            f"Performed {2} hops of retrieval with {len(first_hop_queries)} initial "
            f"and {len(refined_queries)} refined queries. Collected {len(all_results)} results "
            f"across {len(provenance_records)} unique sources."
        )

        output = RetrieverOutput(
            results=all_results,
            provenance_records=provenance_records,
            refinement_queries=all_queries,
            total_hops_performed=1 + int(bool(hop2_results)),
            reasoning=reasoning,
        )

        output.metadata.update({
            "first_hop_queries": first_hop_queries,
            "second_hop_queries": refined_queries,
            "first_hop_confidence": hop1_confidence,
            "second_hop_confidence": hop2_confidence,
            "redundant_chunks": redundant_chunks,
            "insufficient_evidence": insufficient_evidence,
            "conflicting_evidence": conflicting_evidence,
        })

        self.exec_logger.log_event(
            agent_id=self.agent_id,
            event_type="retrieval_complete",
            token_count=0,
            job_id=shared_context.job_id,
            extra={
                "total_results": len(all_results),
                "unique_sources": len(provenance_records),
                "hops": 2,
                "queries": len(all_queries),
            },
        )

        self._logger.info("retrieval complete: %d results from %d sources", len(all_results), len(provenance_records))

        return output

    def _extract_initial_queries(self, sub_tasks: list[Any]) -> list[str]:
        """Extract search queries from sub-task descriptions.

        Simple heuristic: use the description or metadata intent + entities.

        Returns:
            List of initial search queries.
        """
        queries = []

        for task in sub_tasks:
            if task.description:
                # Use cleaned description as query
                query = task.description.strip()
                # Remove intent prefix if present
                query = re.sub(r"^\[.*?\]\s*", "", query)
                if query:
                    queries.append(query)
            elif task.metadata.get("entities"):
                # Fallback: use entities as query
                query = " ".join(task.metadata["entities"])
                if query:
                    queries.append(query)

        return queries if queries else ["general search"]

    async def _execute_retrieval_hop(
        self, queries: list[str], hop_number: int, shared_context: SharedContext
    ) -> list[RetrievalResult]:
        """Execute a single retrieval hop for all queries.

        Args:
            queries: List of search queries
            hop_number: Which hop this is (1=first, 2=refined)
            shared_context: For logging and traceability

        Returns:
            List of RetrievalResult objects
        """
        results = []

        for query in queries:
            payload = {"query": query}

            retry_policy = RetryPolicy(max_retries=2, backoff_seconds=1.0)
            tool_result = await self.execute_tool(self.web_search_tool, payload, retry=retry_policy)

            # Log tool call
            shared_context.tool_call_log.append(
                ToolCallRecord(
                    tool_name="web_search",
                    input=payload,
                    output=tool_result.result if tool_result.result else None,
                    failure=tool_result.failure_mode.value if tool_result.failure_mode else None,
                    latency_ms=tool_result.latency_ms,
                )
            )

            # Parse results if successful
            if tool_result.result and isinstance(tool_result.result, dict):
                search_results = tool_result.result.get("results", [])

                for i, sr in enumerate(search_results):
                    result = RetrievalResult(
                        query=query,
                        source_url=sr.get("url", f"source_{uuid.uuid4()}"),
                        snippet=sr.get("snippet", ""),
                        confidence=float(sr.get("relevance_score", 0.8)),
                        hop_number=hop_number,
                        source_title=sr.get("title", "Untitled"),
                        metadata={
                            "position": i,
                            "query": query,
                        },
                    )
                    results.append(result)

        self._logger.debug("hop %d: retrieved %d results from %d queries", hop_number, len(results), len(queries))

        return results

    def _refine_queries(self, original_queries: list[str], hop1_results: list[RetrievalResult]) -> list[str]:
        """Refine queries for second hop based on first-hop coverage.

        Strategy:
        - If few results from a query, expand with synonyms
        - If results mention related topics, create targeted queries
        - If coverage is weak (low avg confidence), broaden the query

        Returns:
            List of refined search queries for hop 2.
        """
        refined = []

        # Group results by query
        results_by_query = {}
        for result in hop1_results:
            q = result.query
            if q not in results_by_query:
                results_by_query[q] = []
            results_by_query[q].append(result)

        for query in original_queries:
            query_results = results_by_query.get(query, [])

            # If few results or low confidence, broaden the query
            if len(query_results) < 2 or sum(r.confidence for r in query_results) / max(len(query_results), 1) < 0.7:
                # Simple expansion: add generic modifiers
                refined_query = f"{query} overview"
                refined.append(refined_query)
            elif len(query_results) >= 3:
                # Good coverage; try a more specific refinement
                # Extract common keywords from results
                snippets = " ".join(r.snippet[:50] for r in query_results[:2])
                # Simple heuristic: add a specificity term
                refined_query = f"{query} detailed"
                refined.append(refined_query)

        return refined

    def _extract_initial_queries(self, sub_tasks: list[Any]) -> list[str]:
        """Extract search queries from sub-task descriptions."""
        import re

        queries = []

        for task in sub_tasks:
            if task.description:
                query = task.description.strip()
                query = re.sub(r"^\[.*?\]\s*", "", query)
                if query:
                    queries.append(query)
            elif task.metadata.get("entities"):
                query = " ".join(task.metadata["entities"])
                if query:
                    queries.append(query)

        return queries if queries else ["general search"]
