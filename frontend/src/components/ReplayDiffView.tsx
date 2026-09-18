import { useState } from "react";
import { runQuery, compareTraces, type QueryResult, type CompareResult } from "../api";

interface Props {
  defaultQuery: string;
}

export default function ReplayDiffView({ defaultQuery }: Props) {
  const [query, setQuery] = useState(defaultQuery);
  const [runA, setRunA] = useState<QueryResult | null>(null);
  const [runB, setRunB] = useState<QueryResult | null>(null);
  const [comparison, setComparison] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runBoth = async () => {
    setLoading(true);
    setError(null);
    setComparison(null);
    try {
      const [a, b] = await Promise.all([runQuery(query), runQuery(query)]);
      setRunA(a);
      setRunB(b);
      const result = await compareTraces(a, b);
      setComparison(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-1">Replay / Diff</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Runs the same query twice and compares the execution traces via <code className="font-mono">/api/v1/replay/compare</code>,
        which wraps <code className="font-mono">evaluation/replay.py</code>. Under the deterministic (stub) backend, two runs of
        the same query should make identical routing decisions and get identical tool results — proving the orchestration layer
        is reproducible even though wall-clock timing differs every run.
      </p>

      <div className="flex gap-2 mb-3">
        <input
          className="flex-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-sm"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Query to run twice"
        />
        <button
          onClick={runBoth}
          disabled={loading || !query.trim()}
          className="rounded bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm px-3 py-1.5"
        >
          {loading ? "Running both..." : "Run twice & compare"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</p>}

      {comparison && (
        <div>
          <div
            className={`rounded px-3 py-2 text-sm font-medium mb-3 ${
              comparison.identical
                ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                : "bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200"
            }`}
          >
            {comparison.identical
              ? "Identical — both runs made the same decisions and got the same results."
              : `Diverged — ${comparison.divergence_count} difference(s) found.`}
          </div>

          {comparison.divergences.length > 0 && (
            <ul className="text-xs text-gray-600 dark:text-gray-300 mb-3 list-disc pl-4 space-y-0.5">
              {comparison.divergences.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded border border-gray-100 dark:border-gray-800 p-2">
              <div className="font-semibold text-gray-500 dark:text-gray-400 mb-1">Run A</div>
              <div className="font-mono truncate">hash: {comparison.trace1_hash ?? runA?.execution_hash}</div>
              <div>agents: {comparison.trace1_agents?.join(", ")}</div>
              <div>tool calls: {comparison.trace1_tools}</div>
              <div>valid: {String(comparison.trace_a_valid)}</div>
            </div>
            <div className="rounded border border-gray-100 dark:border-gray-800 p-2">
              <div className="font-semibold text-gray-500 dark:text-gray-400 mb-1">Run B</div>
              <div className="font-mono truncate">hash: {comparison.trace2_hash ?? runB?.execution_hash}</div>
              <div>agents: {comparison.trace2_agents?.join(", ")}</div>
              <div>tool calls: {comparison.trace2_tools}</div>
              <div>valid: {String(comparison.trace_b_valid)}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
