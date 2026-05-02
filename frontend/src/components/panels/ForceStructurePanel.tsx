import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HealthBar } from "@/components/ui/HealthBar";
import { DataGrid } from "@/components/ui/DataGrid";
import type { Platform, PlatformClass } from "@/types";
import { Search, Navigation, Square, RotateCcw, X, Loader2 } from "lucide-react";
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

export function ForceStructurePanel() {
  const { platforms, selectedPlatformId, selectPlatform } = useGameStore();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("ALL");

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

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="panel-header">
        <span className="panel-title">Force Structure</span>
        <span className="text-2xs font-mono text-surface-400">{usPlatforms.length} units</span>
      </div>

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
        {Object.entries(grouped).map(([cls, units]) => (
          <div key={cls}>
            <div className="px-3 py-1 bg-surface-800/50 border-b border-surface-700">
              <span className="text-2xs font-mono uppercase tracking-widest text-surface-400">
                {CLASS_LABELS[cls as PlatformClass] ?? cls} ({units.length})
              </span>
            </div>
            {units.map((p) => (
              <button
                key={p.id}
                onClick={() => selectPlatform(p.id === selectedPlatformId ? null : p.id)}
                className={`w-full text-left px-3 py-2 border-b border-surface-800 hover:bg-surface-800 transition-colors ${
                  p.id === selectedPlatformId ? "bg-accent-blue/10 border-l-2 border-l-accent-blue" : ""
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
        ))}
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
            <span className="text-xs font-mono font-semibold text-surface-100">
              {selectedPlatform.designation}
            </span>
            <StatusBadge status={selectedPlatform.status} />
          </div>

          {/* Health/fuel bars */}
          <div className="p-2 space-y-1">
            <HealthBar value={selectedPlatform.health} label="Hull" />
            <HealthBar value={selectedPlatform.fuel_state} label="Fuel" />
          </div>

          {/* Stats */}
          <DataGrid
            rows={[
              { key: "Class", value: selectedPlatform.type_key },
              { key: "Heading", value: selectedPlatform.heading != null ? `${Math.round(selectedPlatform.heading)}°` : "—" },
              { key: "Speed", value: selectedPlatform.speed != null ? `${Math.round(selectedPlatform.speed)} kts` : "—" },
            ]}
          />

          {/* Order buttons — only for non-destroyed platforms */}
          {selectedPlatform.status !== "DESTROYED" && selectedPlatform.status !== "RETIRED" && (
            <OrderButtons platform={selectedPlatform} />
          )}
        </div>
      )}
    </div>
  );
}

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

  return (
    <div className="p-2 border-t border-surface-800">
      <div className="text-2xs font-mono text-surface-500 uppercase tracking-widest mb-1.5">
        Issue Order
      </div>
      <div className="grid grid-cols-2 gap-1">
        {/* MOVE TO — activates map waypoint mode */}
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
      {isInMoveMode && (
        <p className="text-2xs font-mono text-accent-blue mt-1.5 text-center animate-pulse">
          Click destination on map
        </p>
      )}
    </div>
  );
}
