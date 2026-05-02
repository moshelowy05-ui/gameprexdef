import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Mission } from "@/types";
import { Plus, Target, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

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

const MISSION_TYPES = ["STRIKE", "PATROL", "INTERCEPT", "RECON", "ESCORT", "SEAD", "ASW"] as const;

const INPUT_CLS =
  "w-full bg-surface-800 border border-surface-700 rounded px-2 py-1 text-xs font-mono text-surface-100 focus:outline-none focus:border-accent-blue";

interface MissionFormData {
  name: string;
  mission_type: string;
  assigned_tf_id: string;
  target_lon: string;
  target_lat: string;
  priority: string;
  commander_notes: string;
  start_tick: string;
}

export function MissionsPanel() {
  const { missions, selectedMissionId, selectMission, taskForces, activeGame } = useGameStore();
  const [filter, setFilter] = useState<string>("ALL");
  const [showForm, setShowForm] = useState(false);

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
        <button
          className="btn-primary text-2xs"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? <X className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
          {showForm ? "Cancel" : "New"}
        </button>
      </div>

      {/* Creation form — slide-down */}
      {showForm && (
        <MissionForm
          gameId={activeGame?.id ?? ""}
          currentTick={activeGame?.current_tick ?? 0}
          taskForces={taskForces}
          onClose={() => setShowForm(false)}
        />
      )}

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

function MissionForm({
  gameId,
  currentTick,
  taskForces,
  onClose,
}: {
  gameId: string;
  currentTick: number;
  taskForces: Record<string, { id: string; name: string }>;
  onClose: () => void;
}) {
  const tfList = Object.values(taskForces);

  const [form, setForm] = useState<MissionFormData>({
    name: "",
    mission_type: "STRIKE",
    assigned_tf_id: tfList[0]?.id ?? "",
    target_lon: "0",
    target_lat: "0",
    priority: "5",
    commander_notes: "",
    start_tick: String(currentTick),
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (field: keyof MissionFormData) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gameId) {
      setError("No active game.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createMission(gameId, {
        name: form.name.trim(),
        mission_type: form.mission_type,
        assigned_tf_id: form.assigned_tf_id,
        target: { lon: parseFloat(form.target_lon), lat: parseFloat(form.target_lat) },
        priority: parseInt(form.priority, 10),
        start_tick: parseInt(form.start_tick, 10),
        commander_notes: form.commander_notes.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create mission.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-surface-900 border-b border-surface-700 px-3 py-3 space-y-2"
    >
      <div className="text-2xs font-mono uppercase tracking-widest text-surface-400 mb-1">
        New Mission
      </div>

      {/* Name */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Name</label>
        <input
          type="text"
          required
          value={form.name}
          onChange={set("name")}
          className={INPUT_CLS}
          placeholder="e.g. STRIKE ALPHA"
        />
      </div>

      {/* Mission Type */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Mission Type</label>
        <select value={form.mission_type} onChange={set("mission_type")} className={INPUT_CLS}>
          {MISSION_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Task Force */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Task Force</label>
        <select value={form.assigned_tf_id} onChange={set("assigned_tf_id")} className={INPUT_CLS}>
          {tfList.length === 0 && (
            <option value="">— No task forces —</option>
          )}
          {tfList.map((tf) => (
            <option key={tf.id} value={tf.id}>{tf.name}</option>
          ))}
        </select>
      </div>

      {/* Target */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-2xs font-mono text-surface-400 mb-0.5">Target Lon</label>
          <input
            type="number"
            required
            min={-180}
            max={180}
            step="any"
            value={form.target_lon}
            onChange={set("target_lon")}
            className={INPUT_CLS}
          />
        </div>
        <div>
          <label className="block text-2xs font-mono text-surface-400 mb-0.5">Target Lat</label>
          <input
            type="number"
            required
            min={-90}
            max={90}
            step="any"
            value={form.target_lat}
            onChange={set("target_lat")}
            className={INPUT_CLS}
          />
        </div>
      </div>

      {/* Priority + Start Tick */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-2xs font-mono text-surface-400 mb-0.5">Priority</label>
          <input
            type="number"
            required
            min={1}
            max={10}
            value={form.priority}
            onChange={set("priority")}
            className={INPUT_CLS}
          />
        </div>
        <div>
          <label className="block text-2xs font-mono text-surface-400 mb-0.5">Start Tick</label>
          <input
            type="number"
            required
            min={0}
            value={form.start_tick}
            onChange={set("start_tick")}
            className={INPUT_CLS}
          />
        </div>
      </div>

      {/* Notes */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Notes (optional)</label>
        <textarea
          rows={2}
          value={form.commander_notes}
          onChange={set("commander_notes")}
          className={`${INPUT_CLS} resize-none`}
          placeholder="Commander notes..."
        />
      </div>

      {/* Error */}
      {error && (
        <div className="text-2xs font-mono text-accent-red bg-accent-red/10 border border-accent-red/30 rounded px-2 py-1">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary text-2xs flex items-center gap-1 disabled:opacity-50"
        >
          {submitting && <Loader2 className="w-3 h-3 animate-spin" />}
          Submit
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-2 py-1 text-2xs font-mono rounded bg-surface-700 hover:bg-surface-600 text-surface-300 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
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
