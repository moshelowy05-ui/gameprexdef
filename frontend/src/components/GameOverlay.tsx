import { useGameStore } from "@/store/gameStore";
import { Shield, AlertTriangle, Minus } from "lucide-react";

export function GameOverlay() {
  const gameOver = useGameStore((s) => s.gameOver);

  if (!gameOver) return null;

  const isUSWin = gameOver.winner === "US";
  const isDraw = gameOver.winner === "DRAW";

  const bgClass = isUSWin
    ? "from-blue-950/95 to-surface-950/95"
    : isDraw
    ? "from-amber-950/95 to-surface-950/95"
    : "from-red-950/95 to-surface-950/95";

  const icon = isUSWin ? (
    <Shield className="w-24 h-24 text-accent-blue mx-auto mb-6" />
  ) : isDraw ? (
    <Minus className="w-24 h-24 text-accent-amber mx-auto mb-6" />
  ) : (
    <AlertTriangle className="w-24 h-24 text-accent-red mx-auto mb-6" />
  );

  const titleColor = isUSWin ? "text-accent-blue" : isDraw ? "text-accent-amber" : "text-accent-red";

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-gradient-to-br from-black/70 to-black/90">
      <div className={`bg-gradient-to-br ${bgClass} border border-surface-700 rounded-lg p-12 max-w-lg w-full mx-4 text-center shadow-2xl`}>
        {icon}
        <div className="text-2xs font-mono text-surface-500 uppercase tracking-widest mb-2">
          SIMULATION COMPLETE — T+{gameOver.tick}
        </div>
        <h1 className={`text-4xl font-bold font-mono uppercase tracking-widest mb-2 ${titleColor}`}>
          {gameOver.winner === "US"
            ? "US VICTORY"
            : gameOver.winner === "ADVERSARY"
            ? "ADVERSARY VICTORY"
            : "STALEMATE"}
        </h1>
        <p className="text-surface-300 text-sm font-mono mb-8">{gameOver.reason}</p>

        <div className="grid grid-cols-2 gap-4 mb-8">
          <div className="bg-surface-900/60 rounded p-4">
            <div className="stat-label text-accent-blue">US LOSSES</div>
            <div className="text-3xl font-mono font-bold text-surface-100">{gameOver.us_losses}</div>
          </div>
          <div className="bg-surface-900/60 rounded p-4">
            <div className="stat-label text-accent-red">PLAN LOSSES</div>
            <div className="text-3xl font-mono font-bold text-surface-100">{gameOver.plan_losses}</div>
          </div>
        </div>

        <button
          onClick={() => window.location.href = "/"}
          className="w-full py-3 px-6 bg-surface-700 hover:bg-surface-600 text-surface-100 font-mono text-sm uppercase tracking-widest rounded transition-colors"
        >
          Return to Lobby
        </button>
      </div>
    </div>
  );
}
