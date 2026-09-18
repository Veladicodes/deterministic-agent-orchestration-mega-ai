import type { QueryResult } from "../api";

interface Props {
  provenanceLinks: QueryResult["provenance_links"];
}

export default function ProvenancePanel({ provenanceLinks }: Props) {
  const entries = Object.entries(provenanceLinks || {});

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-sm text-gray-500 dark:text-gray-400">
        No provenance links recorded for this answer.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">
        Provenance ({entries.length} source{entries.length === 1 ? "" : "s"})
      </h3>
      <div className="space-y-2">
        {entries.map(([key, record]) => (
          <div
            key={key}
            className="rounded border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-2.5 text-xs"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-gray-700 dark:text-gray-200 truncate">{record.source_id || key}</span>
              <span className="shrink-0 ml-2 px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">
                weight {record.weight?.toFixed?.(2) ?? record.weight}
              </span>
            </div>
            {record.metadata && Object.keys(record.metadata).length > 0 && (
              <pre className="text-[10px] text-gray-500 dark:text-gray-400 whitespace-pre-wrap break-all">
                {JSON.stringify(record.metadata, null, 0)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
