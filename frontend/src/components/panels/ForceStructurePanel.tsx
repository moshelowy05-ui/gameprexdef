import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HealthBar } from "@/components/ui/HealthBar";
import { DataGrid } from "@/components/ui/DataGrid";
import type { Platform, PlatformClass, TaskForce } from "@/types";
import { Search, Navigation, Square, RotateCcw, X, Loader2, Plus, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";

const CLASS_LABELS: Record<PlatformClass, string> = {
  SHIP:       "Naval Surface",
  SUBMARINE:  "Submarine",
  AIRCRAFT:   "Air Wing",
  UAV:        "UAV / Drone",
  VEHICLE:    "Ground Force",
  MISSILE:    "Missiles",
  SATELLITE:  "Space / Satellite",
  FACILITY:   "Facilities",
};

const TF_STATUS_COLORS: Record<string, string> = {
  ASSEMBLING: "text-accent-amber",
  READY:      "text-accent-green",
  UNDERWAY:   "text-accent-blue",
  ENGAGED:    "text-accent-red",
  DISPERSED:  "text-surface-400",
  RETURNED:   "text-surface-400",
};

export function ForceStructurePanel() {
  const { platforms, taskForces, selectedPlatformId, selectedPlatformIds, selectPlatform, setPlatformSelection, activeGame } = useGameStore();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("ALL");
  const [activeTab, setActiveTab] = useState<"platforms" | "taskforces">("platforms");

  const usPlatforms = Object.values(platforms).filter((p) => p.faction === "US");

  const filtered = usPlatforms.filter((p) => {
    const matchesSearch =
      !search ||
      p.designation.toLowerCase().includes(search.toLowerCase()) ||
      p.type_key.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = filter === "ALL" || p.platform_class === filter;
    return matchesSearch && matchesFilter;
  });

  const grouped = filtered.reduce<Record<string, Platform[]>>((acc, p) => {
    const k = p.platform_class;
    if (!acc[k]) acc[k] = [];
    acc[k].push(p);
    return acc;
  }, {});

  const selectedPlatform = selectedPlatformId ? platforms[selectedPlatformId] : null;

  // Find which TF the selected platform belongs to
  const selectedPlatformTf = selectedPlatform
    ? Object.values(taskForces).find((tf) => tf.assigned_unit_ids.includes(selectedPlatform.id)) ?? null
    : null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="panel-header">
        <span className="panel-title">Force Structure</span>
        <span className="text-2xs font-mono text-surface-400">{usPlatforms.length} units</span>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-surface-700 bg-surface-900">
        <button
          onClick={() => setActiveTab("platforms")}
          className={`flex-1 py-1.5 text-2xs font-mono uppercase tracking-widest transition-colors ${
            activeTab === "platforms"
              ? "text-accent-blue border-b-2 border-accent-blue bg-surface-800"
              : "text-surface-400 hover:text-surface-200"
          }`}
        >
          Platforms
        </button>
        <button
          onClick={() => setActiveTab("taskforces")}
          className={`flex-1 py-1.5 text-2xs font-mono uppercase tracking-widest transition-colors ${
            activeTab === "taskforces"
              ? "text-accent-blue border-b-2 border-accent-blue bg-surface-800"
              : "text-surface-400 hover:text-surface-200"
          }`}
        >
          Task Forces
        </button>
      </div>

      {activeTab === "platforms" ? (
        <>
          {/* Search + filter */}
          <div className="p-2 space-y-2 border-b border-surface-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-surface-500" />
              <input
                type="text"
                placeholder="Search units..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-surface-800 border border-surface-600 rounded px-2 py-1 pl-6 text-xs font-mono text-surface-200 placeholder-surface-500 focus:outline-none focus:border-accent-blue"
              />
            </div>
            <div className="flex gap-1 flex-wrap">
              {["ALL", "SHIP", "SUBMARINE", "AIRCRAFT", "UAV", "VEHICLE"].map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-1.5 py-0.5 text-2xs font-mono rounded transition-colors ${
                    filter === f
                      ? "bg-accent-blue text-white"
                      : "text-surface-400 hover:text-surface-200 bg-surface-800 hover:bg-surface-700"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Platform list */}
          <div className="flex-1 overflow-y-auto">
            {Object.entries(grouped).map(([cls, units]) => {
              const aliveIds = units.filter((u) => u.status !== "DESTROYED").map((u) => u.id);
              const allSelected = aliveIds.length > 0 && aliveIds.every((id) => selectedPlatformIds.includes(id));
              return (
              <div key={cls}>
                <button
                  onClick={() => setPlatformSelection(allSelected ? [] : aliveIds)}
                  className="w-full flex items-center justify-between px-3 py-1 bg-surface-800/50 border-b border-surface-700 hover:bg-surface-800 transition-colors group"
                  title={allSelected ? "Deselect group" : "Select all in this group"}
                >
                  <span className="text-2xs font-mono uppercase tracking-widest text-surface-400 group-hover:text-surface-200">
                    {CLASS_LABELS[cls as PlatformClass] ?? cls} ({units.length})
                  </span>
                  <span className={`text-2xs font-mono ${allSelected ? "text-accent-blue" : "text-surface-600 group-hover:text-accent-blue"}`}>
                    {allSelected ? "✓ ALL" : "SELECT ALL"}
                  </span>
                </button>
                {units.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => selectPlatform(p.id === selectedPlatformId ? null : p.id)}
                    className={`w-full text-left px-3 py-2 border-b border-surface-800 hover:bg-surface-800 transition-colors ${
                      selectedPlatformIds.includes(p.id) ? "bg-accent-blue/10 border-l-2 border-l-accent-blue" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-surface-100 truncate">{p.designation}</span>
                      <StatusBadge status={p.status} />
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <HealthBar value={p.fuel_state} label="Fuel" className="flex-1" />
                    </div>
                  </button>
                ))}
              </div>
            );})}
            {filtered.length === 0 && (
              <div className="px-3 py-6 text-center text-surface-500 text-xs font-mono">
                No units found
              </div>
            )}
          </div>

          {/* Detail pane */}
          {selectedPlatform && (
            <div className="border-t border-surface-700 bg-surface-950">
              {/* Platform header */}
              <div className="px-3 py-2 border-b border-surface-800 flex items-center justify-between">
                <div>
                  <div className="text-xs font-mono font-semibold text-surface-100">
                    {selectedPlatform.designation}
                  </div>
                  <div className="text-2xs font-mono text-surface-400">{selectedPlatform.type_key}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xs font-mono text-surface-400 uppercase">{selectedPlatform.faction}</span>
                  <StatusBadge status={selectedPlatform.status} />
                </div>
              </div>

              {/* Health/fuel bars */}
              <div className="p-2 space-y-1">
                <HealthBar value={selectedPlatform.health} label="Hull" />
                <HealthBar value={selectedPlatform.fuel_state} label="Fuel" />
              </div>

              {/* Stats */}
              <DataGrid
                rows={[
                  { key: "Heading",  value: selectedPlatform.heading != null ? `${Math.round(selectedPlatform.heading)}°` : "—" },
                  { key: "Speed",    value: selectedPlatform.speed != null ? `${Math.round(selectedPlatform.speed)} kts` : "—" },
                  { key: "Position", value: selectedPlatform.position ? `[${selectedPlatform.position[0].toFixed(2)}, ${selectedPlatform.position[1].toFixed(2)}]` : "—" },
                  { key: "Task Force", value: selectedPlatformTf ? selectedPlatformTf.name : "Unassigned" },
                ]}
              />

              {/* Order buttons — only for non-destroyed platforms */}
              {selectedPlatform.status !== "DESTROYED" && selectedPlatform.status !== "RETIRED" && (
                <OrderButtons platform={selectedPlatform} />
              )}
            </div>
          )}
        </>
      ) : (
        <TaskForcesTab
          taskForces={Object.values(taskForces)}
          platforms={platforms}
          gameId={activeGame?.id ?? null}
        />
      )}
    </div>
  );
}

// ── Task Forces Tab ───────────────────────────────────────────────────────────

interface TaskForcesTabProps {
  taskForces: TaskForce[];
  platforms: Record<string, Platform>;
  gameId: string | null;
}

function TaskForcesTab({ taskForces, platforms, gameId }: TaskForcesTabProps) {
  const [expandedTfId, setExpandedTfId] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newTfName, setNewTfName] = useState("");
  const [newTfCommander, setNewTfCommander] = useState("");
  const [addPlatformFor, setAddPlatformFor] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loadingRemove, setLoadingRemove] = useState<string | null>(null);
  const [loadingAdd, setLoadingAdd] = useState<string | null>(null);

  const { setTaskForces } = useGameStore();

  const usPlatforms = Object.values(platforms).filter((p) => p.faction === "US");

  // Platforms not in any TF
  const assignedIds = new Set(taskForces.flatMap((tf) => tf.assigned_unit_ids));
  const unassignedPlatforms = usPlatforms.filter((p) => !assignedIds.has(p.id));

  const refreshTaskForces = async () => {
    if (!gameId) return;
    const updated = await api.listTaskForces(gameId) as TaskForce[];
    setTaskForces(updated);
  };

  const handleCreate = async () => {
    if (!gameId || !newTfName.trim() || !newTfCommander) return;
    setCreating(true);
    try {
      await api.createTaskForce(gameId, { name: newTfName.trim(), commander_unit_id: newTfCommander });
      await refreshTaskForces();
      setNewTfName("");
      setNewTfCommander("");
      setShowNewForm(false);
    } finally {
      setCreating(false);
    }
  };

  const handleRemove = async (tfId: string, platformId: string) => {
    if (!gameId) return;
    setLoadingRemove(platformId);
    try {
      await api.removeFromTaskForce(gameId, tfId, platformId);
      await refreshTaskForces();
    } finally {
      setLoadingRemove(null);
    }
  };

  const handleAdd = async (tfId: string, platformId: string) => {
    if (!gameId || !platformId) return;
    setLoadingAdd(tfId);
    try {
      await api.addToTaskForce(gameId, tfId, [platformId]);
      await refreshTaskForces();
      setAddPlatformFor(null);
    } finally {
      setLoadingAdd(null);
    }
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* New TF button */}
      <div className="p-2 border-b border-surface-700">
        <button
          onClick={() => setShowNewForm((v) => !v)}
          className="w-full flex items-center justify-center gap-1 px-2 py-1.5 text-2xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-600 hover:border-accent-blue rounded transition-colors"
        >
          <Plus className="w-3 h-3" />
          New Task Force
        </button>

        {/* Slide-down new TF form */}
        {showNewForm && (
          <div className="mt-2 p-2 bg-surface-900 border border-surface-700 rounded space-y-2">
            <div>
              <label className="text-2xs font-mono text-surface-400 uppercase tracking-widest block mb-0.5">
                Name
              </label>
              <input
                type="text"
                placeholder="TF-77 Bravo..."
                value={newTfName}
                onChange={(e) => setNewTfName(e.target.value)}
                className="w-full bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs font-mono text-surface-200 placeholder-surface-500 focus:outline-none focus:border-accent-blue"
              />
            </div>
            <div>
              <label className="text-2xs font-mono text-surface-400 uppercase tracking-widest block mb-0.5">
                Commander Unit
              </label>
              <select
                value={newTfCommander}
                onChange={(e) => setNewTfCommander(e.target.value)}
                className="w-full bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs font-mono text-surface-200 focus:outline-none focus:border-accent-blue"
              >
                <option value="">— Select Unit —</option>
                {usPlatforms.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.designation} ({p.type_key})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-1">
              <button
                onClick={handleCreate}
                disabled={creating || !newTfName.trim() || !newTfCommander}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1 text-2xs font-mono bg-accent-blue hover:bg-accent-blue/80 text-white rounded disabled:opacity-50 transition-colors"
              >
                {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                Create
              </button>
              <button
                onClick={() => setShowNewForm(false)}
                className="px-2 py-1 text-2xs font-mono bg-surface-700 hover:bg-surface-600 text-surface-300 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* TF list */}
      <div className="flex-1 overflow-y-auto">
        {taskForces.length === 0 && (
          <div className="px-3 py-6 text-center text-surface-500 text-xs font-mono">
            No task forces
          </div>
        )}
        {taskForces.map((tf) => {
          const isExpanded = expandedTfId === tf.id;
          const statusColor = TF_STATUS_COLORS[tf.status] ?? "text-surface-400";
          // Platforms available to add to this specific TF (unassigned globally)
          const availableToAdd = unassignedPlatforms;

          return (
            <div key={tf.id} className="border-b border-surface-800">
              {/* TF row */}
              <button
                onClick={() => setExpandedTfId(isExpanded ? null : tf.id)}
                className={`w-full text-left px-3 py-2 hover:bg-surface-800 transition-colors flex items-center gap-2 ${
                  isExpanded ? "bg-surface-800/60" : ""
                }`}
              >
                {isExpanded
                  ? <ChevronDown className="w-3 h-3 text-surface-400 shrink-0" />
                  : <ChevronRight className="w-3 h-3 text-surface-400 shrink-0" />
                }
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono text-surface-100 truncate">{tf.name}</span>
                    <span className={`text-2xs font-mono uppercase ${statusColor} shrink-0`}>{tf.status}</span>
                  </div>
                  <div className="text-2xs font-mono text-surface-400 mt-0.5">
                    {tf.assigned_unit_ids.length} unit{tf.assigned_unit_ids.length !== 1 ? "s" : ""}
                  </div>
                </div>
              </button>

              {/* Expanded TF detail */}
              {isExpanded && (
                <div className="bg-surface-950 border-t border-surface-800 px-3 py-2 space-y-1">
                  {/* Assigned platforms */}
                  {tf.assigned_unit_ids.length === 0 && (
                    <div className="text-2xs font-mono text-surface-500 py-1">No units assigned</div>
                  )}
                  {tf.assigned_unit_ids.map((pid) => {
                    const p = platforms[pid];
                    return (
                      <div key={pid} className="flex items-center justify-between gap-2 py-0.5">
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-mono text-surface-200 truncate block">
                            {p ? p.designation : pid}
                          </span>
                          {p && (
                            <span className="text-2xs font-mono text-surface-500">{p.type_key}</span>
                          )}
                        </div>
                        <button
                          onClick={() => handleRemove(tf.id, pid)}
                          disabled={loadingRemove === pid}
                          className="p-0.5 text-surface-500 hover:text-accent-red transition-colors disabled:opacity-50 shrink-0"
                          title="Remove from task force"
                        >
                          {loadingRemove === pid
                            ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <X className="w-3 h-3" />
                          }
                        </button>
                      </div>
                    );
                  })}

                  {/* Add platform */}
                  <div className="pt-1 border-t border-surface-800">
                    {addPlatformFor === tf.id ? (
                      <div className="flex items-center gap-1">
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) handleAdd(tf.id, e.target.value);
                          }}
                          disabled={loadingAdd === tf.id}
                          className="flex-1 bg-surface-800 border border-surface-600 rounded px-1.5 py-1 text-2xs font-mono text-surface-200 focus:outline-none focus:border-accent-blue"
                        >
                          <option value="">— Add Platform —</option>
                          {availableToAdd.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.designation} ({p.type_key})
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => setAddPlatformFor(null)}
                          className="p-1 text-surface-500 hover:text-surface-200 transition-colors"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setAddPlatformFor(tf.id)}
                        className="w-full flex items-center justify-center gap-1 px-2 py-1 text-2xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-700 hover:border-surface-500 rounded transition-colors"
                      >
                        <Plus className="w-3 h-3" />
                        Add Platform
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Order Buttons ─────────────────────────────────────────────────────────────

function OrderButtons({ platform }: { platform: Platform }) {
  const { activeGame, orderMode, setOrderMode, clearOrderMode } = useGameStore();
  const [loading, setLoading] = useState<string | null>(null);

  const gameId = activeGame?.id;
  if (!gameId) return null;

  const isInMoveMode =
    orderMode.active &&
    orderMode.platformId === platform.id &&
    orderMode.orderType === "MOVE_TO";

  const issue = async (
    orderType: "HOLD" | "RTB" | "ABORT",
  ) => {
    setLoading(orderType);
    try {
      await api.submitOrder(gameId, platform.id, { order_type: orderType, priority: 200 });
    } finally {
      setLoading(null);
    }
  };

  const handleMoveClick = () => {
    if (isInMoveMode) {
      clearOrderMode();
    } else {
      setOrderMode({ active: true, platformId: platform.id, orderType: "MOVE_TO" });
    }
  };

  // Wrap ALL JSX in a fragment so there’s never an adjacency error
  return (
    <>
      <div className="p-2 border-t border-surface-800">
        <div className="text-2xs font-mono text-surface-500 uppercase tracking-widest mb-1.5">
          Issue Order
        </div>
        <div className="grid grid-cols-2 gap-1">
          {/* MOVE TO */}
          <button
            onClick={handleMoveClick}
            className={`flex items-center gap-1 px-2 py-1.5 rounded text-2xs font-mono transition-colors ${
              isInMoveMode
                ? "bg-accent-blue text-white"
                : "bg-surface-700 hover:bg-surface-600 text-surface-200"
            }`}
          >
            <Navigation className="w-3 h-3" />
            {isInMoveMode ? "Click Map..." : "Move To"}
          </button>

          {/* HOLD */}
          <button
            onClick={() => issue("HOLD")}
            disabled={loading === "HOLD"}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-2xs font-mono bg-surface-700 hover:bg-surface-600 text-surface-200 transition-colors disabled:opacity-50"
          >
            {loading === "HOLD" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
            Hold
          </button>

          {/* RTB */}
          <button
            onClick={() => issue("RTB")}
            disabled={loading === "RTB"}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-2xs font-mono bg-surface-700 hover:bg-surface-600 text-accent-amber transition-colors disabled:opacity-50"
          >
            {loading === "RTB" ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
            RTB
          </button>

          {/* CANCEL */}
          <button
            onClick={() => issue("ABORT")}
            disabled={loading === "ABORT"}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-2xs font-mono bg-surface-700 hover:bg-surface-600 text-accent-red transition-colors disabled:opacity-50"
          >
            {loading === "ABORT" ? <Loader2 className="w-3 h-3 animate-spin" /> : <X className="w-3 h-3" />}
            Cancel
          </button>
        </div>
      </div>
      {isInMoveMode && (
        <p className="text-2xs font-mono text-accent-blue mt-1.5 text-center animate-pulse">
          Click destination on map
        </p>
      )}
    </>
  );
}

