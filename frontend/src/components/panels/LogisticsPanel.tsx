import { useGameStore } from "@/store/gameStore";

export function LogisticsPanel() {
  const { platforms } = useGameStore();
  const allPlatforms = Object.values(platforms);

  // Fleet fuel summary
  const fueled = allPlatforms.filter(p => p.status !== "DESTROYED" && p.fuel_state != null);
  const avgFuel = fueled.length ? fueled.reduce((s, p) => s + (p.fuel_state ?? 1), 0) / fueled.length : 0;
  const critical = fueled.filter(p => (p.fuel_state ?? 1) < 0.10);    // BINGO
  const low = fueled.filter(p => (p.fuel_state ?? 1) >= 0.10 && (p.fuel_state ?? 1) < 0.20);  // LOW
  const rtb = allPlatforms.filter(p => (p.status as string) === "RTB");

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Logistics</span>
      </div>
      {/* Fleet fuel overview */}
      <div className="grid grid-cols-2 gap-px bg-surface-700 border-b border-surface-700">
        {[
          { label: "Avg Fuel",  value: `${(avgFuel * 100).toFixed(0)}%`, color: avgFuel < 0.2 ? "text-accent-red" : "text-surface-100" },
          { label: "BINGO",     value: critical.length,                   color: critical.length > 0 ? "text-accent-red" : "text-surface-400" },
          { label: "Low Fuel",  value: low.length,                        color: low.length > 0 ? "text-accent-amber" : "text-surface-400" },
          { label: "RTB",       value: rtb.length,                        color: "text-surface-100" },
        ].map(stat => (
          <div key={stat.label} className="bg-surface-900 px-3 py-2">
            <div className={`text-sm font-mono font-semibold ${stat.color}`}>{stat.value}</div>
            <div className="text-2xs font-mono text-surface-500 uppercase">{stat.label}</div>
          </div>
        ))}
      </div>
      {/* BINGO platforms list */}
      <div className="flex-1 overflow-y-auto">
        {critical.length === 0 && low.length === 0 && (
          <div className="px-3 py-8 text-center">
            <p className="text-xs font-mono text-surface-500">All platforms nominal</p>
          </div>
        )}
        {[...critical, ...low].map(p => (
          <div key={p.id} className={`flex items-center justify-between px-3 py-2 border-b border-surface-800 ${(p.fuel_state ?? 1) < 0.10 ? "bg-accent-red/5" : ""}`}>
            <div>
              <span className="text-xs font-mono text-surface-100">{p.designation || p.type_key}</span>
              <span className="ml-2 text-2xs font-mono text-surface-400">{p.type_key}</span>
            </div>
            <span className={`text-xs font-mono font-semibold ${(p.fuel_state ?? 1) < 0.10 ? "text-accent-red" : "text-accent-amber"}`}>
              {((p.fuel_state ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
