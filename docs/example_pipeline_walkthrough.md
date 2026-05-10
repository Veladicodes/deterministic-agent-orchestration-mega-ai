# Full Pipeline Walkthrough: PostgreSQL vs Redis

This document walks through a complete execution of the multi-agent orchestration system on a realistic query.

**Query**: "Compare PostgreSQL and Redis for caching workloads"

This query is complex enough to showcase the system's strengths and reveal its design philosophy.

---

## Step 1: Input Query

```
User Input:
"Compare PostgreSQL and Redis for caching workloads"

Query ID: example_001
Category: normal (well-formed, factual)
```

### What's Happening

The query is submitted to the API endpoint. The system receives a string and begins orchestration.

**Key design point**: The query is deterministic input. Any query sent with identical text will produce identical execution traces (same agents run, same tool calls, same results).

---

## Step 2: Decomposer Agent Output

The Decomposer Agent breaks the query into structured sub-tasks.

```json
{
  "decomposition_id": "job_001_decompose",
  "query_id": "example_001",
  "original_query": "Compare PostgreSQL and Redis for caching workloads",
  "main_tasks": [
    {
      "task_id": "task_1",
      "description": "Retrieve PostgreSQL characteristics for caching",
      "type": "retrieval"
    },
    {
      "task_id": "task_2",
      "description": "Retrieve Redis characteristics for caching",
      "type": "retrieval"
    },
    {
      "task_id": "task_3",
      "description": "Identify comparison points (performance, consistency, operability)",
      "type": "analysis"
    }
  ],
  "comparison_points": [
    "query performance",
    "data consistency model",
    "operational complexity",
    "scalability approach",
    "use case fit"
  ],
  "ambiguity_flags": [],
  "execution_order": ["task_1", "task_2", "task_3"],
  "confidence": 0.95
}
```

### Analysis

- **3 sub-tasks** identified (retrieval focus + comparison analysis)
- **No ambiguity** detected (clear, factual query)
- **High confidence** (0.95): query is well-formed
- **Deterministic**: This decomposition will be identical on every execution

**Latency**: ~85ms (rule-based pattern matching)

---

## Step 3: Retriever Agent Output

The Retriever Agent executes tool calls to gather evidence.

```json
{
  "retrieval_id": "job_001_retrieve",
  "timestamp": "2026-05-09T14:23:45Z",
  "retrieved_results": [
    {
      "search_task": "task_1",
      "query": "PostgreSQL caching performance ACID",
      "tool_calls": [
        {
          "tool": "WebSearchTool",
          "arguments": {
            "query": "PostgreSQL as cache storage characteristics",
            "limit": 3
          },
          "attempt": 1,
          "duration_ms": 245,
          "status": "success"
        }
      ],
      "results": [
        {
          "source": "https://postgresql.org/docs/performance",
          "title": "PostgreSQL Performance Tuning",
          "snippet": "PostgreSQL provides ACID compliance with row-level locking...",
          "confidence": 0.88,
          "relevance": "high"
        },
        {
          "source": "https://example.com/postgres-cache",
          "title": "Using PostgreSQL as a Cache Layer",
          "snippet": "PostgreSQL can serve as a caching layer with TTL support...",
          "confidence": 0.82,
          "relevance": "high"
        },
        {
          "source": "https://benchmark.example.com",
          "title": "PostgreSQL vs Redis Benchmarks",
          "snippet": "In caching workloads, Redis outperforms PostgreSQL 10x...",
          "confidence": 0.79,
          "relevance": "high"
        }
      ]
    },
    {
      "search_task": "task_2",
      "query": "Redis caching performance data structure",
      "tool_calls": [
        {
          "tool": "WebSearchTool",
          "arguments": {
            "query": "Redis caching architecture performance",
            "limit": 3
          },
          "attempt": 1,
          "duration_ms": 198,
          "status": "success"
        }
      ],
      "results": [
        {
          "source": "https://redis.io/topics/performance",
          "title": "Redis Performance",
          "snippet": "Redis operates on in-memory data structures with O(1) operations...",
          "confidence": 0.92,
          "relevance": "high"
        },
        {
          "source": "https://redis.io/topics/persistence",
          "title": "Redis Persistence Options",
          "snippet": "Redis offers RDB and AOF for data durability...",
          "confidence": 0.88,
          "relevance": "medium"
        },
        {
          "source": "https://blog.example.com/redis-guide",
          "title": "Redis Caching Best Practices",
          "snippet": "Redis shines in high-throughput caching scenarios...",
          "confidence": 0.75,
          "relevance": "medium"
        }
      ]
    }
  ],
  "total_tool_calls": 2,
  "retries": 0,
  "retry_reason": null,
  "completion_rate": 1.0
}
```

### Analysis

- **2 tool calls** executed (1 per retrieval task)
- **0 retries** needed (both successful on first attempt)
- **6 results** total gathered
- **Confidence range**: 0.75–0.92 (strong sources)

**Key observation**: The source credibility varies. benchmark.example.com (0.79) is slightly lower confidence than redis.io (0.92). This informs later stages.

**Latency**: ~450ms (includes network roundtrips)

---

## Step 4: Critic Agent Output

The Critic Agent analyzes results for contradictions, gaps, and provenance issues.

```json
{
  "criticism_id": "job_001_critique",
  "timestamp": "2026-05-09T14:23:52Z",
  "analysis": {
    "contradictions_detected": [
      {
        "id": "contradiction_1",
        "severity": "medium",
        "type": "performance_comparison",
        "claim_a": {
          "source": "benchmark.example.com",
          "statement": "Redis outperforms PostgreSQL 10x in caching",
          "confidence": 0.79
        },
        "claim_b": {
          "source": "postgresql.org",
          "statement": "PostgreSQL provides ACID compliance",
          "confidence": 0.88,
          "context": "ACID compliance comes at performance cost vs pure caching"
        },
        "resolution": "Not a contradiction; different design tradeoffs. Both statements true in different contexts.",
        "flagged_for_synthesis": false
      }
    ],
    "provenance_coverage": {
      "total_claims": 6,
      "sourced_claims": 6,
      "coverage_percentage": 1.0,
      "weak_sources": [
        {
          "source_id": "blog.example.com",
          "confidence": 0.75,
          "reason": "blog post, not official documentation",
          "recommendation": "include but flag as secondary source"
        }
      ]
    },
    "low_confidence_threshold": 0.3,
    "flagged_claims": [],
    "confidence_assessment": {
      "overall_confidence": 0.85,
      "rationale": "Multiple authoritative sources (redis.io, postgresql.org), good coverage, no contradictions"
    }
  },
  "summary": {
    "contradictions": 1,
    "actual_contradictions": 0,
    "provenance_gaps": 0,
    "low_confidence_claims": 0,
    "recommendation": "proceed_to_synthesis"
  }
}
```

### Analysis

- **1 detected contradiction**: Redis vs PostgreSQL performance
  - **Resolution**: Not actually a contradiction; different design philosophies
  - **Rationale**: Flagged as context-dependent tradeoff, not a factual conflict

- **100% provenance coverage**: All 6 claims have sources

- **1 weak source**: blog.example.com (confidence 0.75)
  - **Recommendation**: Include but mark as secondary

- **Overall confidence**: 0.85 (high)

**Key insight**: The Critic doesn't just flag contradictions; it reasons about whether they're real or context-dependent. This is rule-based but sufficient for deterministic analysis.

**Latency**: ~95ms (rule matching and analysis)

---

## Step 5: Synthesizer Agent Output

The Synthesizer Agent produces the final answer with full provenance attribution.

```json
{
  "synthesis_id": "job_001_synthesize",
  "timestamp": "2026-05-09T14:23:54Z",
  "structured_answer": {
    "query": "Compare PostgreSQL and Redis for caching workloads",
    "answer_text": "PostgreSQL and Redis serve different caching philosophies:\n\n**Redis** is optimized for pure caching speed. It stores data in memory using optimized data structures (hashes, lists, sets) with O(1) operations, delivering 10x performance improvement over PostgreSQL in high-throughput scenarios [source: benchmark.example.com, confidence 0.79].\n\n**PostgreSQL** sacrifices speed for reliability. It enforces ACID compliance with row-level locking, ensuring data consistency and durability [source: postgresql.org, confidence 0.88]. PostgreSQL can serve as a cache layer with TTL support, but at lower throughput [source: example.com/postgres-cache, confidence 0.82].\n\n**Summary**: For pure caching speed, Redis is the clear winner. For caching scenarios requiring strict consistency guarantees, PostgreSQL is appropriate despite performance tradeoffs.",
    "comparison_structure": {
      "redis": {
        "strengths": [
          "O(1) in-memory operations",
          "10x performance vs PostgreSQL in caching",
          "Simple operational model (single node or cluster)",
          "Built-in persistence options (RDB, AOF)"
        ],
        "strengths_sources": [
          "redis.io/topics/performance [0.92]",
          "benchmark.example.com [0.79]",
          "redis.io/topics/persistence [0.88]"
        ],
        "weaknesses": [
          "No ACID compliance",
          "Data lost on node failure (without persistence)"
        ]
      },
      "postgresql": {
        "strengths": [
          "ACID compliance ensures data consistency",
          "TTL support for cache expiration",
          "Query language flexibility"
        ],
        "strengths_sources": [
          "postgresql.org/docs/performance [0.88]",
          "example.com/postgres-cache [0.82]"
        ],
        "weaknesses": [
          "10x slower than Redis in caching workloads",
          "Higher operational complexity"
        ]
      }
    },
    "provenance": [
      {
        "claim_index": 1,
        "statement": "Redis stores data in memory with O(1) operations",
        "source": "https://redis.io/topics/performance",
        "confidence": 0.92,
        "claim_type": "technical_specification"
      },
      {
        "claim_index": 2,
        "statement": "Redis outperforms PostgreSQL 10x in caching",
        "source": "https://benchmark.example.com",
        "confidence": 0.79,
        "claim_type": "benchmark"
      },
      {
        "claim_index": 3,
        "statement": "PostgreSQL provides ACID compliance",
        "source": "https://postgresql.org/docs/performance",
        "confidence": 0.88,
        "claim_type": "technical_specification"
      },
      {
        "claim_index": 4,
        "statement": "PostgreSQL can serve as cache with TTL",
        "source": "https://example.com/postgres-cache",
        "confidence": 0.82,
        "claim_type": "use_case"
      },
      {
        "claim_index": 5,
        "statement": "Redis offers RDB and AOF persistence",
        "source": "https://redis.io/topics/persistence",
        "confidence": 0.88,
        "claim_type": "technical_specification"
      }
    ],
    "caveats": [
      "Performance comparison (10x) is workload-dependent; not all caching scenarios show this ratio",
      "PostgreSQL performance can be optimized with proper configuration",
      "One source is from a blog; official documentation should be primary reference"
    ],
    "confidence_score": 0.85,
    "removed_claims": [],
    "ambiguity_notes": []
  }
}
```

### Analysis

- **Comprehensive answer** structured with comparison points
- **Full provenance**: Every claim linked to source + confidence
- **5 provenance-linked claims** with confidence scores (0.79–0.92)
- **3 caveats** noted (workload dependency, optimization, source type)
- **Confidence score**: 0.85 (high, reflects authoritative sources)
- **No low-confidence claims removed** (all above 0.3 threshold)

**Key insight**: The answer isn't just text; it's structured with provenance metadata. Users can:
- See exactly where each claim comes from
- Evaluate source reliability via confidence scores
- Understand caveats and ambiguity

**Latency**: ~120ms (template assembly, no network calls)

---

## Step 6: Execution Trace

Every execution produces an immutable trace for replay and debugging.

```json
{
  "replay_id": "job_001",
  "original_job_id": "job_001",
  "query": "Compare PostgreSQL and Redis for caching workloads",
  "agent_sequence": [
    "decomposer",
    "retriever",
    "critic",
    "synthesizer"
  ],
  "tool_calls": [
    {
      "tool_id": "tool_001",
      "tool_name": "WebSearchTool",
      "input": {"query": "PostgreSQL as cache storage characteristics", "limit": 3},
      "output": [
        {"source": "https://postgresql.org/docs/performance", "title": "PostgreSQL Performance Tuning", ...},
        ...
      ],
      "duration_ms": 245,
      "status": "success"
    },
    {
      "tool_id": "tool_002",
      "tool_name": "WebSearchTool",
      "input": {"query": "Redis caching architecture performance", "limit": 3},
      "output": [...],
      "duration_ms": 198,
      "status": "success"
    }
  ],
  "state_transitions": [
    {"state": "INITIALIZED", "timestamp": "2026-05-09T14:23:40Z"},
    {"state": "DECOMPOSING", "timestamp": "2026-05-09T14:23:41Z"},
    {"state": "RETRIEVING", "timestamp": "2026-05-09T14:23:42Z"},
    {"state": "CRITIQUING", "timestamp": "2026-05-09T14:23:52Z"},
    {"state": "SYNTHESIZING", "timestamp": "2026-05-09T14:23:53Z"},
    {"state": "COMPLETED", "timestamp": "2026-05-09T14:23:54Z"}
  ],
  "execution_path": {
    "deterministic": true,
    "agents": ["decomposer", "retriever", "critic", "synthesizer"],
    "retries": 0,
    "tool_failures": 0,
    "agent_sequence_deviation": false
  },
  "created_at": "2026-05-09T14:23:40Z",
  "replayed_at": null,
  "replay_successful": null,
  "replay_divergence": null
}
```

### Analysis

- **Deterministic sequence**: decomposer → retriever → critic → synthesizer (always same order)
- **2 tool calls** recorded with full inputs/outputs
- **6 state transitions** tracked with timestamps
- **No retries** needed
- **14 seconds wall-clock time** (40ms + 450ms + 95ms + 120ms + overhead)

**Key insight**: This trace is immutable. Later, if someone asks "what happened on query 001?", we can replay it deterministically using this trace.

---

## Step 7: Pipeline Metrics

Structured metrics collected for the full pipeline.

```json
{
  "job_id": "job_001",
  "total_latency_ms": 755,
  "decomposer_latency_ms": 85,
  "retriever_latency_ms": 450,
  "critic_latency_ms": 95,
  "synthesizer_latency_ms": 120,
  "orchestration_latency_ms": 5,
  "retry_count": 0,
  "tool_failure_count": 0,
  "partial_failure_occurred": false,
  "completion_rate": 1.0,
  "provenance_coverage": 1.0,
  "orchestration_success": true,
  "decomposition_completeness": 0.95,
  "retrieval_relevance_estimate": 0.85,
  "contradiction_detection_rate": 1.0,
  "synthesis_completeness": 0.92,
  "confidence_score": 0.85,
  "timestamp": "2026-05-09T14:23:54Z",
  "metadata": {
    "category": "normal",
    "query_id": "example_001"
  }
}
```

### Analysis

| Metric | Value | Interpretation |
|--------|-------|---|
| **total_latency_ms** | 755ms | Under 1s; well within 2s threshold |
| **breakdown** | R:450, S:120, C:95, D:85 | Retrieval dominates (network), agents fast |
| **retry_count** | 0 | No failures encountered |
| **provenance_coverage** | 100% | All claims sourced |
| **contradiction_detection_rate** | 100% | All contradictions detected (even context-dependent ones) |
| **synthesis_completeness** | 92% | Covered 9 of 10 comparison points |
| **confidence_score** | 0.85 | High confidence; authoritative sources |

---

## Step 8: Evaluation Metrics Summary

When running full evaluation on 40-query dataset, this query contributes to aggregate statistics.

```json
{
  "query_category": "normal",
  "category_performance": {
    "success": true,
    "latency_contribution_percentile": "p50",
    "retry_contribution": 0,
    "failure_type": null
  },
  "aggregate_impact": {
    "normal_category_success_rate": "10/10",
    "avg_latency_ms": 450,
    "p95_latency_ms": 890,
    "provenance_coverage_contribution": 1.0,
    "confidence_distribution": "0.85 (high confidence)"
  }
}
```

---

## Step 9: How Replay Works

If a reviewer wants to understand what happened in this execution, they can replay it:

```bash
python scripts/replay_query.py \
  --trace-id job_001 \
  --operation validate \
  --evaluation-id eval_run_20260509
```

**Output**:
```json
{
  "trace_id": "job_001",
  "valid": true,
  "agent_count": 4,
  "tool_call_count": 2,
  "agent_sequence": ["decomposer", "retriever", "critic", "synthesizer"],
  "state_transitions": 6,
  "execution_deterministic": true
}
```

The replayer:
1. ✅ Validates trace structure (agents, tools, states)
2. ✅ Verifies all fields present
3. ✅ Confirms deterministic execution path
4. ✅ Can be compared to original execution to detect any divergence

---

## Step 10: Failure Scenario

What if retrieval had failed? Example:

```json
{
  "job_id": "job_002_hypothetical_failure",
  "retriever_call": {
    "attempt": 1,
    "status": "timeout",
    "duration_ms": 5000,
    "error": "WebSearchTool exceeded 5s timeout"
  },
  "retry_sequence": [
    {
      "attempt": 2,
      "backoff_ms": 100,
      "status": "timeout",
      "duration_ms": 4950
    },
    {
      "attempt": 3,
      "backoff_ms": 200,
      "status": "success",
      "duration_ms": 2100,
      "result_count": 5
    }
  ],
  "total_latency_ms": 12450,
  "retry_count": 2,
  "failure_type": null,
  "final_status": "success_after_retry"
}
```

The RetryCoordinator:
1. Attempts retrieval (fails at 5s)
2. Waits 100ms, retries (fails at 4.95s)
3. Waits 200ms, retries (succeeds at 2.1s)
4. Proceeds to next agent

**Result**: Query still completes despite transient failure. Retry overhead: ~5.2s additional latency.

**Classification**: `FailureType.TIMEOUT_FAILURE` → recoverable via retry

---

## Key Takeaways

### System Strengths Demonstrated

✅ **Deterministic Execution**: Same query produces identical traces  
✅ **Full Provenance**: Every claim linked to source  
✅ **Contradiction Awareness**: Context-dependent conflicts detected  
✅ **Observable**: Complete execution trace and metrics  
✅ **Replayable**: Immutable traces enable debugging  
✅ **Fault Tolerant**: Automatic retry with exponential backoff  

### Design Tradeoffs Visible

⚖️ **Deterministic ordering** means less flexible orchestration, but fully traceable execution  
⚖️ **Rule-based critique** simpler than semantic analysis, but explicit and testable  
⚖️ **Fixed agent sequence** limits dynamic behavior, but eliminates orchestration bugs  
⚖️ **Behavioral evaluation** avoids exact-match brittleness, but requires upfront dataset curation  

### What a Reviewer Learns

1. The system executes in a fixed, predictable order
2. Every step produces structured output with metadata
3. Failures are classified and recoverable
4. Execution traces enable offline debugging
5. Metrics drive observability and improvement

---

For more information:
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [EVALUATION.md](../EVALUATION.md)
- [docs/architecture_diagram.md](architecture_diagram.md)
