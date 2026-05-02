import { useGameStore } from "@/store/gameStore";

export function CombatLogPanel() {
  const combatEvents = useGameStore((s) => s.combatEvents);

  const recentEvents = [...combatEvents].reverse().slice(0, 50);

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Combat Log</span>
        <span className="text-2xs font-mono text-surface-400">{combatEvents.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1 font-mono text-2xs">
        {recentEvents.length === 0 ? (
          <p className="text-surface-500 p-2">No engagements recorded.</p>
        ) : (
          recentEvents.map((ev, i) => (
            <div
              key={i}
              className={`p-2 rounded border ${
                ev.hit && ev.damage >= 0.5
                  ? "border-accent-red/30 bg-accent-red/5 text-accent-red"
                  : ev.hit
                  ? "border-accent-amber/30 bg-accent-amber/5 text-accent-amber"
                  : "border-surface-700 text-surface-500"
              }`}
            >
              <span className="text-surface-600 mr-2">T+{ev.tick}</span>
              {ev.narrative}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
