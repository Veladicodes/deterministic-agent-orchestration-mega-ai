import { useState } from "react";
import { runQuery, streamQuery, type QueryResult, type StreamEvent } from "./api";
import PipelineTimeline, { reduceStreamEvents } from "./components/PipelineTimeline";
import ProvenancePanel from "./components/ProvenancePanel";
import ReplayDiffView from "./components/ReplayDiffView";

type Tab = "run" | "replay";

const EXAMPLE_QUERY = "What is machine learning?";

function App() {
  const [query, setQuery] = useState(EXAMPLE_QUERY);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("run");

  const handleRun = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setEvents([]);
    setResult(null);

    try {
      // Two calls, two pipeline runs: /query/stream gives live per-stage
      // events but no structured final result; /query/run gives the full
      // result (answer, provenance, execution_hash) but no live events.
      // Acceptable for a demo since the deterministic stub path is fast
      // and cheap; a real deployment wanting one run per click would need
      // /query/stream to carry the final result in its last event instead.
      await streamQuery(query, (event) => {
        setEvents((prev) => [...prev, event]);
      });
      const finalResult = await runQuery(query);
      setResult(finalResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const { stages, routingDecisions } = reduceStreamEvents(events);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <header className="mb-6">
          <h1 className="text-xl font-bold">Deterministic Agent Orchestration</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            A fixed, replayable pipeline — decomposer &rarr; retriever &rarr; critic &rarr; synthesizer. Every run is traced,
            hashed, and comparable to any other run of the same query.
          </p>
        </header>

        <nav className="flex gap-1 mb-4 border-b border-gray-200 dark:border-gray-800">
          {(["run", "replay"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t
                  ? "border-purple-600 text-purple-600 dark:text-purple-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {t === "run" ? "Run a query" : "Replay / diff"}
            </button>
          ))}
        </nav>

        {tab === "run" && (
          <>
            <div className="flex gap-2 mb-4">
              <input
                className="flex-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRun()}
                placeholder="Ask something..."
              />
              <button
                onClick={handleRun}
                disabled={loading || !query.trim()}
                className="rounded bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm px-4 py-2"
              >
                {loading ? "Running..." : "Run"}
              </button>
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400 mb-4">{error}</p>}

            {events.length > 0 && (
              <div className="mb-4">
                <PipelineTimeline
                  stages={stages}
                  routingDecisions={routingDecisions}
                  agentEvents={result?.execution_trace.agent_events}
                />
              </div>
            )}

            {result && (
              <div className="space-y-4">
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-300">Answer</h3>
                    {result.confidence_score != null && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">
                        confidence {result.confidence_score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{result.final_answer}</p>
                  <p className="text-[11px] text-gray-400 mt-2 font-mono truncate">execution_hash: {result.execution_hash}</p>
                </div>

                <ProvenancePanel provenanceLinks={result.provenance_links} />
              </div>
            )}
          </>
        )}

        {tab === "replay" && <ReplayDiffView defaultQuery={query} />}
      </div>
    </div>
  );
}

export default App;
