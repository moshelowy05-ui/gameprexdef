import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { clsx } from "clsx";

type Filter = "all" | "hit" | "kill" | "miss";

const FILTER_LABELS: Record<Filter, string> = {
  all:  "All",
  hit:  "Hits",
  kill: "Kills",
  miss: "Misses",
};

export function CombatLogPanel() {
  const combatEvents = useGameStore((s) => s.combatEvents);
  const [filter, setFilter] = useState<Filter>("all");

  const hits   = combatEvents.filter((e) => e.hit).length;
  const misses  = combatEvents.filter((e) => !e.hit).length;
  const kills   = combatEvents.filter((e) => e.hit && e.target_health_after <= 0).length;

  const filtered = [...combatEvents].reverse().filter((e) => {
    if (filter === "hit")  return e.hit;
    if (filter === "kill") return e.hit && e.target_health_after <= 0;
    if (filter === "miss") return !e.hit;
    return true;
  }).slice(0, 60);

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Combat Log</span>
        <span className="text-2xs font-mono text-surface-400">{combatEvents.length} events</span>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-px bg-surface-700 border-b border-surface-700 shrink-0">
        <div className="bg-surface-900 p-2 text-center">
          <div className="text-base font-mono font-bold text-accent-amber">{hits}</div>
          <div className="text-2xs font-mono text-surface-500 uppercase">Hits</div>
        </div>
        <div className="bg-surface-900 p-2 text-center">
          <div className="text-base font-mono font-bold text-accent-red">{kills}</div>
          <div className="text-2xs font-mono text-surface-500 uppercase">Kills</div>
        </div>
        <div className="bg-surface-900 p-2 text-center">
          <div className="text-base font-mono font-bold text-surface-400">{misses}</div>
          <div className="text-2xs font-mono text-surface-500 uppercase">Misses</div>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex border-b border-surface-700 shrink-0">
        {(Object.keys(FILTER_LABELS) as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "flex-1 py-1 text-2xs font-mono transition-colors",
              filter === f
                ? "text-accent-blue border-b-2 border-accent-blue -mb-px bg-accent-blue/5"
                : "text-surface-500 hover:text-surface-300",
            )}
          >
            {FILTER_LABELS[f]}
          </button>
        ))}
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 font-mono text-2xs">
        {filtered.length === 0 ? (
          <p className="text-surface-500 p-2">No events match filter.</p>
        ) : (
          filtered.map((ev, i) => {
            const isKill   = ev.hit && ev.target_health_after <= 0;
            const isHeavy  = ev.hit && ev.damage >= 0.5;
            return (
              <div
                key={i}
                className={clsx(
                  "p-2 rounded border",
                  isKill   ? "border-accent-red/50 bg-accent-red/10 text-accent-red" :
                  isHeavy  ? "border-accent-amber/40 bg-accent-amber/8 text-accent-amber" :
                  ev.hit   ? "border-accent-amber/20 bg-accent-amber/5 text-accent-amber/80" :
                             "border-surface-700 text-surface-500",
                )}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-surface-600">T+{ev.tick}</span>
                  {isKill  && <span className="px-1 bg-accent-red/20 text-accent-red rounded text-2xs">KILL</span>}
                  {isHeavy && !isKill && <span className="px-1 bg-accent-amber/20 text-accent-amber rounded text-2xs">HIT</span>}
                  {!ev.hit && <span className="px-1 bg-surface-700 text-surface-500 rounded text-2xs">MISS</span>}
                  {ev.hit && (
                    <span className="ml-auto text-surface-600">
                      -{Math.round(ev.damage * 100)}% HP
                    </span>
                  )}
                </div>
                <div className="leading-relaxed">{ev.narrative}</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
