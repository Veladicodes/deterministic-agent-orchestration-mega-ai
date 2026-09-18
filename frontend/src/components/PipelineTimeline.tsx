import type { AgentEvent, StreamEvent } from "../api";

const STAGES = ["decomposer", "retriever", "critic", "synthesizer"] as const;
type Stage = (typeof STAGES)[number];

export interface StageState {
  status: "pending" | "running" | "skipped" | "done";
}

export function reduceStreamEvents(events: StreamEvent[]): {
  stages: Record<Stage, StageState>;
  routingDecisions: StreamEvent[];
} {
  const stages: Record<Stage, StageState> = {
    decomposer: { status: "pending" },
    retriever: { status: "pending" },
    critic: { status: "pending" },
    synthesizer: { status: "pending" },
  };
  const routingDecisions: StreamEvent[] = [];

  for (const event of events) {
    if (event.event_type === "agent_started") {
      const id = event.agent_id as Stage;
      if (id in stages) stages[id].status = "running";
    } else if (event.event_type === "agent_completed") {
      const id = event.agent_id as Stage;
      if (id in stages) stages[id].status = "done";
    } else if (event.event_type === "routing_decision") {
      routingDecisions.push(event);
      const action = String(event.selected_action || "");
      if (action.startsWith("skip_")) {
        const skipped = action.replace("skip_", "") as Stage;
        if (skipped in stages && stages[skipped].status === "pending") {
          stages[skipped].status = "skipped";
        }
      }
    }
  }

  return { stages, routingDecisions };
}

const STATUS_STYLES: Record<StageState["status"], string> = {
  pending: "bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400",
  running: "bg-blue-500 text-white animate-pulse",
  done: "bg-green-500 text-white",
  skipped: "bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200",
};

interface Props {
  stages: Record<Stage, StageState>;
  routingDecisions: StreamEvent[];
  agentEvents?: AgentEvent[];
}

export default function PipelineTimeline({ stages, routingDecisions, agentEvents }: Props) {
  const latencyFor = (stage: Stage) => agentEvents?.find((e) => e.agent_id === stage)?.latency_ms;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">
        Pipeline stages (deterministic sequence: decomposer &rarr; retriever &rarr; critic &rarr; synthesizer)
      </h3>
      <div className="flex flex-wrap gap-2 mb-4">
        {STAGES.map((stage) => {
          const latency = latencyFor(stage);
          return (
            <div
              key={stage}
              className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1.5 ${STATUS_STYLES[stages[stage].status]}`}
            >
              <span>{stage}</span>
              <span className="opacity-70">
                {stages[stage].status === "skipped" ? "(skipped)" : latency != null ? `${latency.toFixed(0)}ms` : ""}
              </span>
            </div>
          );
        })}
      </div>

      {routingDecisions.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
            Routing decisions
          </h4>
          <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
            {routingDecisions.map((d, i) => (
              <li key={i} className="flex gap-2">
                <span className="font-mono text-blue-600 dark:text-blue-400 shrink-0">{String(d.selected_action)}</span>
                <span className="opacity-70">{String(d.trigger_reason)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
