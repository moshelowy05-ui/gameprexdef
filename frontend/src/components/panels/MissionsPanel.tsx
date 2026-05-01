import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Mission } from "@/types";
import { Plus, Target, ChevronDown } from "lucide-react";

const MISSION_TYPE_COLORS: Record<string, string> = {
  STRIKE:    "text-accent-red",
  PATROL:    "text-accent-blue",
  INTERCEPT: "text-accent-amber",
  RECON:     "text-accent-cyan",
  ESCORT:    "text-accent-green",
  SEAD:      "text-orange-400",
  ASW:       "text-violet-400",
  ISR:       "text-accent-cyan",
  EW:        "text-yellow-400",
};

export function MissionsPanel() {
  const { missions, selectedMissionId, selectMission } = useGameStore();
  const [filter, setFilter] = useState<string>("ALL");

  const allMissions = Object.values(missions);
  const filtered =
    filter === "ALL" ? allMissions : allMissions.filter((m) => m.status === filter);

  const selectedMission = selectedMissionId ? missions[selectedMissionId] : null;

  const statusCounts = allMissions.reduce<Record<string, number>>((acc, m) => {
    acc[m.status] = (acc[m.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Mission Planning</span>
        <button className="btn-primary text-2xs">
          <Plus className="w-3 h-3" /> New
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 px-2 py-2 border-b border-surface-700 overflow-x-auto">
        {["ALL", "PLANNED", "ACTIVE", "COMPLETE", "ABORTED"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`shrink-0 px-2 py-0.5 text-2xs font-mono rounded transition-colors ${
              filter === s
                ? "bg-accent-blue text-white"
                : "text-surface-400 hover:text-surface-200 bg-surface-800"
            }`}
          >
            {s}
            {statusCounts[s] !== undefined && (
              <span className="ml-1 opacity-70">({statusCounts[s]})</span>
            )}
          </button>
        ))}
      </div>

      {/* Mission list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-3 py-8 text-center">
            <Target className="w-6 h-6 mx-auto mb-2 text-surface-600" />
            <p className="text-xs font-mono text-surface-500">No missions</p>
          </div>
        )}
        {filtered.map((m) => (
          <button
            key={m.id}
            onClick={() => selectMission(m.id === selectedMissionId ? null : m.id)}
            className={`w-full text-left px-3 py-2.5 border-b border-surface-800 hover:bg-surface-800 transition-colors ${
              m.id === selectedMissionId ? "bg-accent-blue/10 border-l-2 border-l-accent-blue" : ""
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-mono text-surface-100 truncate">{m.name}</span>
              <StatusBadge status={m.status} />
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`text-2xs font-mono font-semibold ${MISSION_TYPE_COLORS[m.mission_type] ?? "text-surface-400"}`}
              >
                {m.mission_type}
              </span>
              <span className="text-2xs font-mono text-surface-500">PRI:{m.priority}</span>
              <span className="text-2xs font-mono text-surface-500">T+{m.start_tick}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Detail pane */}
      {selectedMission && (
        <MissionDetail mission={selectedMission} />
      )}
    </div>
  );
}

function MissionDetail({ mission }: { mission: Mission }) {
  const { taskForces } = useGameStore();
  const tf = mission.assigned_tf_id ? taskForces[mission.assigned_tf_id] : null;

  return (
    <div className="border-t border-surface-700 bg-surface-950 max-h-64 overflow-y-auto">
      <div className="px-3 py-2 border-b border-surface-800">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-semibold text-surface-100">{mission.name}</span>
          <StatusBadge status={mission.status} />
        </div>
      </div>
      <div className="divide-y divide-surface-800">
        {[
          { key: "Type",      value: mission.mission_type },
          { key: "Task Force", value: tf?.name ?? mission.assigned_tf_id.slice(0, 8) },
          { key: "Priority",  value: mission.priority },
          { key: "Start",     value: `T+${mission.start_tick}` },
          { key: "End",       value: mission.end_tick ? `T+${mission.end_tick}` : "—" },
          { key: "Waypoints", value: (mission.waypoints as unknown[]).length },
        ].map((row) => (
          <div key={row.key} className="flex justify-between px-3 py-1">
            <span className="data-key">{row.key}</span>
            <span className="data-val">{String(row.value)}</span>
          </div>
        ))}
      </div>
      {mission.commander_notes && (
        <div className="px-3 py-2 border-t border-surface-800">
          <p className="text-2xs font-mono text-surface-400">{mission.commander_notes}</p>
        </div>
      )}
    </div>
  );
}
