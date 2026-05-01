import { Activity, Clock, Pause, Play, ChevronRight, Bell, Shield } from "lucide-react";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";

const SPEED_OPTIONS = [0.25, 1, 5, 10, 50];

export function TopBar() {
  const { activeGame, alerts } = useGameStore();
  const unreadCritical = alerts.filter((a) => a.level === "critical").length;

  const criticalAlerts = alerts.filter(a => a.level === "critical").length;

  const handlePause = async () => {
    if (!activeGame) return;
    if (activeGame.paused) {
      await api.resumeGame(activeGame.id);
    } else {
      await api.pauseGame(activeGame.id);
    }
  };

  const handleSpeed = async (multiplier: number) => {
    if (!activeGame) return;
    await api.setSpeed(activeGame.id, multiplier);
  };

  const tickToDateTime = (tick: number) => {
    const hours = tick % 24;
    const days = Math.floor(tick / 24);
    return `D+${days} ${String(hours).padStart(2, "0")}00Z`;
  };

  return (
    <div className="h-10 bg-surface-900 border-b border-surface-700 flex items-center px-4 gap-4 shrink-0">
      {/* Branding */}
      <div className="flex items-center gap-2">
        <Shield className="w-4 h-4 text-accent-blue" />
        <span className="text-xs font-mono font-semibold tracking-widest text-surface-200 uppercase">
          NCA Command
        </span>
      </div>

      <div className="w-px h-5 bg-surface-700" />

      {/* Game clock */}
      <div className="flex items-center gap-1.5">
        <Clock className="w-3.5 h-3.5 text-surface-400" />
        <span className="font-mono text-xs text-surface-200">
          {activeGame ? tickToDateTime(activeGame.current_tick) : "--"}
        </span>
        <span className="text-2xs font-mono text-surface-500 ml-1">
          T+{activeGame?.current_tick ?? 0}
        </span>
      </div>

      <div className="w-px h-5 bg-surface-700" />

      {/* Sim controls */}
      <div className="flex items-center gap-1">
        <button
          onClick={handlePause}
          disabled={!activeGame}
          className="btn-ghost px-2"
          title={activeGame?.paused ? "Resume" : "Pause"}
        >
          {activeGame?.paused ? (
            <Play className="w-3.5 h-3.5" />
          ) : (
            <Pause className="w-3.5 h-3.5" />
          )}
        </button>
        <span className="text-2xs text-surface-500 font-mono">SPEED</span>
        {SPEED_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => handleSpeed(s)}
            disabled={!activeGame}
            className={`px-1.5 py-0.5 text-2xs font-mono rounded transition-colors ${
              activeGame?.tick_speed_multiplier === s
                ? "bg-accent-blue text-white"
                : "text-surface-400 hover:text-surface-200 hover:bg-surface-700"
            }`}
          >
            {s}x
          </button>
        ))}
      </div>

      <div className="flex-1" />

      {/* Scenario */}
      {activeGame && (
        <div className="flex items-center gap-1 text-2xs font-mono text-surface-400">
          <span>SCN:</span>
          <span className="text-surface-200 uppercase">{activeGame.scenario_id}</span>
        </div>
      )}

      <div className="w-px h-5 bg-surface-700" />

      {/* Alerts bell */}
      <button className="relative btn-ghost px-2" title="Alerts">
        <Bell className="w-3.5 h-3.5" />
        {criticalAlerts > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 bg-accent-red rounded-full text-2xs flex items-center justify-center text-white font-bold">
            {criticalAlerts > 9 ? "9+" : criticalAlerts}
          </span>
        )}
      </button>

      {/* Connection indicator */}
      <div className="flex items-center gap-1">
        <Activity className="w-3.5 h-3.5 text-accent-green" />
        <span className="text-2xs font-mono text-accent-green">LIVE</span>
      </div>
    </div>
  );
}
