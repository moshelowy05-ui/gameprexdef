import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Mission } from "@/types";
import { Plus, Target, X, Loader2, MapPin } from "lucide-react";
import { api } from "@/lib/api";
import { clsx } from "clsx";

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

const MISSION_DESCRIPTIONS: Record<string, string> = {
  STRIKE:    "Attack a fixed target",
  PATROL:    "Maintain presence in an area",
  INTERCEPT: "Intercept incoming threat",
  RECON:     "Gather intelligence",
  ESCORT:    "Protect friendly units",
  SEAD:      "Suppress enemy air defenses",
  ASW:       "Anti-submarine warfare",
};

const INPUT_CLS =
  "w-full bg-surface-800 border border-surface-700 rounded px-2 py-1 text-xs font-mono text-surface-100 focus:outline-none focus:border-accent-blue";

let missionCounter = 1;

export function MissionsPanel() {
  const { missions, selectedMissionId, selectMission, activeGame } = useGameStore();
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

      {showForm && (
        <MissionForm
          gameId={activeGame?.id ?? ""}
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
            <p className="text-xs font-mono text-surface-500 mb-1">No missions</p>
            <p className="text-2xs font-mono text-surface-600">Click "New" to create one</p>
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
              {(m.target as {lon?:number})?.lon != null && (
                <span className="text-2xs font-mono text-surface-600">
                  [{((m.target as {lon:number;lat:number}).lon).toFixed(1)}, {((m.target as {lon:number;lat:number}).lat).toFixed(1)}]
                </span>
              )}
            </div>
          </button>
        ))}
      </div>

      {selectedMission && (
        <MissionDetail mission={selectedMission} />
      )}
    </div>
  );
}

function MissionForm({
  gameId,
  onClose,
}: {
  gameId: string;
  onClose: () => void;
}) {
  const { setOrderMode, setPickTargetCallback, clearOrderMode } = useGameStore();

  const defaultName = `MISSION-${missionCounter}`;
  const [name, setName] = useState(defaultName);
  const [missionType, setMissionType] = useState<string>("STRIKE");
  const [target, setTarget] = useState<{ lon: number; lat: number } | null>(null);
  const [priority, setPriority] = useState(5);
  const [notes, setNotes] = useState("");
  const [picking, setPicking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startPickTarget = () => {
    setPicking(true);
    setPickTargetCallback((lon: number, lat: number) => {
      setTarget({ lon: parseFloat(lon.toFixed(4)), lat: parseFloat(lat.toFixed(4)) });
      setPicking(false);
    });
    setOrderMode({ active: true, platformId: null, orderType: "PICK_TARGET" });
  };

  const cancelPick = () => {
    setPicking(false);
    clearOrderMode();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gameId) { setError("No active game."); return; }
    if (!target) { setError("Click 'Pick on Map' to set a target location."); return; }
    setSubmitting(true);
    setError(null);
    try {
      await api.createMission(gameId, {
        name: name.trim() || defaultName,
        mission_type: missionType,
        target,
        priority,
        commander_notes: notes.trim() || undefined,
      });
      missionCounter++;
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
      className="bg-surface-900 border-b border-surface-700 px-3 py-3 space-y-2.5"
    >
      <div className="text-2xs font-mono uppercase tracking-widest text-surface-400 mb-1">
        New Mission
      </div>

      {/* Mission type selector — big buttons */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-1">Type</label>
        <div className="grid grid-cols-4 gap-1">
          {MISSION_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setMissionType(t)}
              title={MISSION_DESCRIPTIONS[t]}
              className={clsx(
                "py-1 text-2xs font-mono rounded border transition-colors",
                missionType === t
                  ? "border-accent-blue bg-accent-blue/20 text-accent-blue"
                  : "border-surface-700 bg-surface-800 text-surface-400 hover:text-surface-200 hover:border-surface-500",
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <p className="text-2xs font-mono text-surface-500 mt-0.5">{MISSION_DESCRIPTIONS[missionType]}</p>
      </div>

      {/* Target — map pick */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-1">Target Location</label>
        {picking ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 px-2 py-1.5 text-2xs font-mono text-accent-blue bg-accent-blue/10 border border-accent-blue/30 rounded animate-pulse">
              Click anywhere on the map...
            </div>
            <button type="button" onClick={cancelPick} className="p-1.5 bg-surface-700 rounded hover:bg-surface-600 transition-colors">
              <X className="w-3 h-3 text-surface-400" />
            </button>
          </div>
        ) : target ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 px-2 py-1.5 text-2xs font-mono text-accent-green bg-accent-green/10 border border-accent-green/30 rounded flex items-center gap-1.5">
              <MapPin className="w-3 h-3 shrink-0" />
              {target.lon.toFixed(3)}, {target.lat.toFixed(3)}
            </div>
            <button type="button" onClick={startPickTarget} className="p-1.5 bg-surface-700 rounded hover:bg-surface-600 transition-colors" title="Re-pick">
              <MapPin className="w-3 h-3 text-surface-400" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={startPickTarget}
            className="w-full flex items-center justify-center gap-1.5 px-2 py-2 text-2xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-600 hover:border-accent-blue rounded transition-colors text-surface-300"
          >
            <MapPin className="w-3 h-3" />
            Pick on Map
          </button>
        )}
      </div>

      {/* Name */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Name (optional)</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={INPUT_CLS}
          placeholder={defaultName}
        />
      </div>

      {/* Priority */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">
          Priority: <span className="text-surface-200">{priority}</span>
          <span className="text-surface-600 ml-1">(1 = low, 10 = critical)</span>
        </label>
        <input
          type="range"
          min={1}
          max={10}
          value={priority}
          onChange={(e) => setPriority(parseInt(e.target.value, 10))}
          className="w-full accent-accent-blue"
        />
      </div>

      {/* Notes */}
      <div>
        <label className="block text-2xs font-mono text-surface-400 mb-0.5">Notes (optional)</label>
        <textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className={`${INPUT_CLS} resize-none`}
          placeholder="Commander notes..."
        />
      </div>

      {error && (
        <div className="text-2xs font-mono text-accent-red bg-accent-red/10 border border-accent-red/30 rounded px-2 py-1">
          {error}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={submitting || picking}
          className="btn-primary text-2xs flex items-center gap-1 disabled:opacity-50"
        >
          {submitting && <Loader2 className="w-3 h-3 animate-spin" />}
          Create Mission
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
  return (
    <div className="border-t border-surface-700 bg-surface-950 max-h-56 overflow-y-auto">
      <div className="px-3 py-2 border-b border-surface-800 flex items-center justify-between">
        <span className="text-xs font-mono font-semibold text-surface-100">{mission.name}</span>
        <StatusBadge status={mission.status} />
      </div>
      <div className="divide-y divide-surface-800">
        {[
          { key: "Type",     value: mission.mission_type },
          { key: "Priority", value: mission.priority },
          { key: "Target",   value: (() => { const t = mission.target as {lon?:number;lat?:number}; return t?.lon != null ? `[${t.lon.toFixed(2)}, ${t.lat?.toFixed(2)}]` : "—"; })() },
          { key: "Start",    value: mission.start_tick != null ? `T+${mission.start_tick}` : "—" },
          { key: "End",      value: mission.end_tick ? `T+${mission.end_tick}` : "—" },
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
