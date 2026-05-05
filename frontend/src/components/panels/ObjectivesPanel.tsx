import { useQuery } from "@tanstack/react-query";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";
import { CheckCircle, XCircle, Circle, AlertCircle, Clock, ChevronDown } from "lucide-react";
import { useState } from "react";
import type { ScenarioObjective, ScenarioEvent } from "@/types";

// ── Style maps ────────────────────────────────────────────────────────────────

const STATUS_ICON: Record<string, React.ReactNode> = {
  COMPLETE: <CheckCircle className="w-3.5 h-3.5 text-accent-green shrink-0" />,
  FAILED:   <XCircle className="w-3.5 h-3.5 text-accent-red shrink-0" />,
  ACTIVE:   <AlertCircle className="w-3.5 h-3.5 text-accent-amber shrink-0" />,
  PENDING:  <Circle className="w-3.5 h-3.5 text-surface-500 shrink-0" />,
};

const STATUS_COLOR: Record<string, string> = {
  COMPLETE: "text-accent-green",
  FAILED:   "text-accent-red",
  ACTIVE:   "text-accent-amber",
  PENDING:  "text-surface-500",
};

const OBJ_TYPE_COLOR: Record<string, string> = {
  STRATEGIC:   "text-accent-red bg-accent-red/10",
  OPERATIONAL: "text-accent-amber bg-accent-amber/10",
  DEFENSIVE:   "text-accent-blue bg-accent-blue/10",
  TACTICAL:    "text-accent-green bg-accent-green/10",
};

const EVT_TYPE_COLOR: Record<string, string> = {
  INTEL:       "border-accent-blue/30 bg-accent-blue/5",
  ALERT:       "border-accent-red/30 bg-accent-red/5",
  DIPLOMATIC:  "border-accent-amber/30 bg-accent-amber/5",
  COMBAT:      "border-accent-red/40 bg-accent-red/10",
  SYSTEM:      "border-surface-700 bg-surface-800/50",
};

const EVT_TYPE_LABEL: Record<string, string> = {
  INTEL:       "text-accent-blue",
  ALERT:       "text-accent-red",
  DIPLOMATIC:  "text-accent-amber",
  COMBAT:      "text-accent-red",
  SYSTEM:      "text-surface-400",
};

const CLASS_COLOR: Record<string, string> = {
  "TOP SECRET // NOFORN": "text-accent-red",
  "TOP SECRET":           "text-accent-red",
  "SECRET // REL AUS JPN":"text-accent-amber",
  "SECRET // REL CAN NOR":"text-accent-amber",
  "SECRET // FVEY":       "text-accent-amber",
  "SECRET":               "text-accent-amber",
  "CONFIDENTIAL":         "text-accent-blue",
  "UNCLASSIFIED // FOUO": "text-surface-400",
  "UNCLASSIFIED":         "text-accent-green",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ObjectiveRow({ obj }: { obj: ScenarioObjective }) {
  const [expanded, setExpanded] = useState(false);
  const progressPct = Math.round(obj.progress * 100);

  return (
    <div className="border border-surface-700 rounded overflow-hidden">
      <button
        className="w-full text-left p-2.5 flex items-start gap-2 hover:bg-surface-800/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {STATUS_ICON[obj.status] ?? STATUS_ICON.PENDING}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-2xs font-mono font-semibold text-surface-100">{obj.id}</span>
            <span className={`text-2xs font-mono px-1 rounded uppercase ${OBJ_TYPE_COLOR[obj.type] ?? "text-surface-400"}`}>
              {obj.type}
            </span>
          </div>
          <div className="text-xs font-mono text-surface-200 mt-0.5 leading-tight">{obj.title}</div>
          {obj.detail && (
            <div className={`text-2xs font-mono mt-0.5 ${STATUS_COLOR[obj.status]}`}>{obj.detail}</div>
          )}
        </div>
        <ChevronDown className={`w-3 h-3 text-surface-500 shrink-0 mt-0.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {/* Progress bar */}
      {obj.status === "ACTIVE" && (
        <div className="px-2.5 pb-1.5">
          <div className="h-0.5 bg-surface-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-amber rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="text-2xs font-mono text-surface-500 mt-0.5">{progressPct}%</div>
        </div>
      )}

      {/* Expanded description */}
      {expanded && (
        <div className="px-2.5 pb-2.5 pt-0 border-t border-surface-700 bg-surface-900">
          <p className="text-2xs font-mono text-surface-400 mt-1.5 leading-relaxed">{obj.description}</p>
        </div>
      )}
    </div>
  );
}

function ScenarioEventCard({ ev }: { ev: ScenarioEvent }) {
  const [expanded, setExpanded] = useState(false);
  const classColor = CLASS_COLOR[ev.classification] ?? "text-surface-400";

  return (
    <div className={`border rounded p-2.5 ${EVT_TYPE_COLOR[ev.type] ?? "border-surface-700"}`}>
      <div className="flex items-start gap-1.5 justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            <span className={`text-2xs font-mono font-semibold uppercase ${EVT_TYPE_LABEL[ev.type]}`}>
              {ev.type}
            </span>
            <span className="text-2xs font-mono text-surface-500">T+{ev.tick}</span>
          </div>
          <div className="text-xs font-mono text-surface-100 font-medium leading-tight">{ev.title}</div>
          <div className={`text-2xs font-mono ${classColor} mt-0.5`}>{ev.classification}</div>
        </div>
        <button
          className="text-surface-500 hover:text-surface-300 shrink-0 mt-0.5"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      </div>

      {expanded && (
        <div className="mt-1.5 border-t border-surface-700/50 pt-1.5 space-y-1">
          <p className="text-2xs font-mono text-surface-300 leading-relaxed">{ev.body}</p>
          <div className="flex items-center gap-1 text-2xs font-mono text-surface-500">
            <Clock className="w-2.5 h-2.5" />
            <span>SOURCE: {ev.source}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

type Tab = "objectives" | "intel";

export function ObjectivesPanel() {
  const { activeGame, scenarioEvents, setObjectives, objectives } = useGameStore();
  const [tab, setTab] = useState<Tab>("objectives");

  useQuery({
    queryKey: ["objectives", activeGame?.id],
    queryFn: async () => {
      const data = await api.getObjectives(activeGame!.id) as {
        objectives: ScenarioObjective[];
        current_tick: number;
        scenario_id: string;
      };
      setObjectives(data.objectives);
      return data;
    },
    enabled: !!activeGame?.id,
    refetchInterval: 15_000,
  });

  const completeCount = objectives.filter(o => o.status === "COMPLETE").length;
  const failedCount = objectives.filter(o => o.status === "FAILED").length;

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Objectives</span>
        <div className="flex items-center gap-1 text-2xs font-mono">
          {completeCount > 0 && (
            <span className="text-accent-green">{completeCount} done</span>
          )}
          {failedCount > 0 && (
            <span className="text-accent-red">{failedCount} failed</span>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-surface-700 shrink-0">
        {(["objectives", "intel"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-2xs font-mono uppercase tracking-wider transition-colors ${
              tab === t
                ? "text-accent-blue border-b-2 border-accent-blue"
                : "text-surface-500 hover:text-surface-300"
            }`}
          >
            {t === "objectives" ? `Objectives (${objectives.length})` : `Intel Log (${scenarioEvents.length})`}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {tab === "objectives" ? (
          objectives.length === 0 ? (
            <p className="text-2xs font-mono text-surface-500 p-2 text-center">Loading objectives…</p>
          ) : (
            objectives.map((obj) => <ObjectiveRow key={obj.id} obj={obj} />)
          )
        ) : (
          scenarioEvents.length === 0 ? (
            <p className="text-2xs font-mono text-surface-500 p-2 text-center">No intel reports received</p>
          ) : (
            scenarioEvents.map((ev) => <ScenarioEventCard key={ev.id ?? `${ev.tick}-${ev.title}`} ev={ev} />)
          )
        )}
      </div>
    </div>
  );
}
