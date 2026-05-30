import { useEffect } from "react";
import { Activity, Clock, Pause, Play, Bell, Shield } from "lucide-react";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";

// 1=1x  2=5x  3=10x  4=25x  5=50x
const SPEED_OPTIONS = [1, 5, 10, 25, 50];
const SPEED_KEY_MAP: Record<string, number> = { "1": 1, "2": 5, "3": 10, "4": 25, "5": 50 };

export function TopBar() {
  const { activeGame, alerts } = useGameStore();
  const criticalAlerts = alerts.filter((a) => a.level === "critical").length;

  const handlePause = async () => {
    if (!activeGame) return;
    if (activeGame.paused) {
      await api.resumeGame(activeGame.id);
      useGameStore.getState().updateTick(activeGame.current_tick, false);
    } else {
      await api.pauseGame(activeGame.id);
      useGameStore.getState().updateTick(activeGame.current_tick, true);
    }
  };

  const handleSpeed = async (multiplier: number) => {
    if (!activeGame) return;
    await api.setSpeed(activeGame.id, multiplier);
    useGameStore.getState().updateSpeed(multiplier);
  };

  // Keyboard shortcuts: 1–5 for speed, Space for pause handled in GamePage
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      const speed = SPEED_KEY_MAP[e.key];
      if (speed !== undefined && activeGame) {
        e.preventDefault();
        handleSpeed(speed);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeGame]);

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
          className={`btn-ghost px-2 ${activeGame?.paused ? "text-accent-amber animate-pulse" : ""}`}
          title={activeGame?.paused ? "Resume [Space]" : "Pause [Space]"}
        >
          {activeGame?.paused ? (
            <Play className="w-3.5 h-3.5" />
          ) : (
            <Pause className="w-3.5 h-3.5" />
          )}
        </button>
        {activeGame?.paused && (
          <span className="text-2xs font-mono text-accent-amber font-semibold animate-pulse">
            PAUSED
          </span>
        )}
        <span className="text-2xs text-surface-500 font-mono ml-1">SPEED</span>
        {SPEED_OPTIONS.map((s, i) => (
          <button
            key={s}
            onClick={() => handleSpeed(s)}
            disabled={!activeGame}
            title={`${s}x speed [${i + 1}]`}
            className={`px-1.5 py-0.5 text-2xs font-mono rounded transition-colors ${
              activeGame?.tick_speed_multiplier === s
                ? "bg-accent-blue text-white"
                : "text-surface-400 hover:text-surface-200 hover:bg-surface-700"
            }`}
          >
            {s}x
          </button>
        ))}
        <span className="text-2xs font-mono text-surface-600 ml-1 hidden xl:inline">
          [1–5]
        </span>
      </div>

      <div className="flex-1" />

      {/* Scenario + threat warning */}
      {activeGame && (
        <div className="flex items-center gap-3">
          {/* Amphibious threat indicator */}
          <AmphibWarning />
          <div className="flex items-center gap-1 text-2xs font-mono text-surface-400">
            <span>SCN:</span>
            <span className="text-surface-200 uppercase">{activeGame.scenario_id}</span>
          </div>
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

/** Flashes a red warning when PLAN amphibious ships are closing on Taiwan. */
function AmphibWarning() {
  const platforms = useGameStore((s) => s.platforms);

  const amphib = Object.values(platforms).filter(
    (p) =>
      p.faction !== "US" &&
      p.status !== "DESTROYED" &&
      p.position &&
      (p.type_key.startsWith("TYPE075") || p.type_key.startsWith("TYPE071")),
  );

  if (amphib.length === 0) return null;

  // Rough distance check: within 500 NM of Taiwan (120.5, 23.5)
  const hasThreaten = amphib.some((p) => {
    if (!p.position) return false;
    const dx = (p.position[0] - 120.5) * Math.cos((23.5 * Math.PI) / 180) * 60;
    const dy = (p.position[1] - 23.5) * 60;
    return Math.sqrt(dx * dx + dy * dy) < 500;
  });

  if (!hasThreaten) return null;

  return (
    <div className="flex items-center gap-1 px-2 py-0.5 bg-accent-red/20 border border-accent-red/40 rounded text-2xs font-mono text-accent-red animate-pulse">
      ⚠ AMPHIB THREAT
    </div>
  );
}
