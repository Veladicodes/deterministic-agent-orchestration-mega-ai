export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export interface RoutingDecision {
  decision_type: string;
  trigger_reason: string;
  confidence: number;
  selected_action: string;
  rejected_actions: string[];
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface ToolCall {
  tool_name: string;
  success: boolean;
  latency_ms: number | null;
  retries: number;
  output: Record<string, unknown> | null;
}

export interface AgentEvent {
  agent_id: string;
  status: string;
  latency_ms: number;
  retries: number;
  token_count: number;
  error: string | null;
}

export interface ExecutionTrace {
  agent_events: AgentEvent[];
  routing_decisions: RoutingDecision[];
  tool_calls: ToolCall[];
  state_transitions: [string, string][];
  [key: string]: unknown;
}

export interface QueryResult {
  job_id: string;
  query: string;
  success: boolean;
  final_answer: string | null;
  confidence_score: number | null;
  provenance_links: Record<string, { source_id: string; weight: number; metadata: Record<string, unknown> }>;
  execution_trace: ExecutionTrace;
  execution_hash: string;
  summary: Record<string, unknown>;
  errors: string[];
  warnings: string[];
}

export interface CompareResult {
  identical: boolean;
  divergence_count: number;
  divergences: string[];
  trace1_agents: string[];
  trace2_agents: string[];
  trace1_tools: number;
  trace2_tools: number;
  trace1_hash: string;
  trace2_hash: string;
  trace_a_valid: boolean;
  trace_b_valid: boolean;
}

export async function runQuery(query: string): Promise<QueryResult> {
  const res = await fetch(`${API_BASE}/query/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function compareTraces(a: QueryResult, b: QueryResult): Promise<CompareResult> {
  const res = await fetch(`${API_BASE}/replay/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      trace_a: { job_id: a.job_id, query: a.query, execution_trace: a.execution_trace },
      trace_b: { job_id: b.job_id, query: b.query, execution_trace: b.execution_trace },
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface StreamEvent {
  event_type: string;
  [key: string]: unknown;
}

export function streamQuery(query: string, onEvent: (event: StreamEvent) => void): Promise<void> {
  return fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  }).then(async (res) => {
    if (!res.body) throw new Error("No response body for stream");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (line) {
          const jsonStr = line.slice("data: ".length);
          try {
            onEvent(JSON.parse(jsonStr));
          } catch {
            // ignore malformed chunk
          }
        }
      }
    }
  });
}
