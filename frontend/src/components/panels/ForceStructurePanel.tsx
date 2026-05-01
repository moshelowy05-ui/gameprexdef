import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HealthBar } from "@/components/ui/HealthBar";
import { DataGrid } from "@/components/ui/DataGrid";
import type { Platform, PlatformClass } from "@/types";
import { ChevronRight, Search } from "lucide-react";

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
          <div className="px-3 py-2 border-b border-surface-800 flex items-center justify-between">
            <span className="text-xs font-mono font-semibold text-surface-100">
              {selectedPlatform.designation}
            </span>
            <StatusBadge status={selectedPlatform.status} />
          </div>
          <div className="p-2 space-y-1">
            <HealthBar value={selectedPlatform.health} label="Hull" />
            <HealthBar value={selectedPlatform.fuel_state} label="Fuel" />
          </div>
          <DataGrid
            rows={[
              { key: "Class", value: selectedPlatform.type_key },
              { key: "Faction", value: selectedPlatform.faction },
              { key: "Heading", value: selectedPlatform.heading != null ? `${selectedPlatform.heading}°` : "—" },
              { key: "Speed", value: selectedPlatform.speed != null ? `${selectedPlatform.speed} kts` : "—" },
              { key: "Alt", value: selectedPlatform.altitude != null ? `${selectedPlatform.altitude.toLocaleString()} ft` : "—" },
              { key: "Maint Due", value: `T+${selectedPlatform.maintenance_due_tick}` },
            ]}
          />
        </div>
      )}
    </div>
  );
}
