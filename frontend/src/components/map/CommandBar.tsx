/**
 * CommandBar — fixed bottom panel showing the selected unit and action buttons.
 * Replaces the previous quick-menu floating popup.
 *
 * Shown when a friendly platform is selected. Action buttons put the map into
 * the appropriate order mode (MOVE_TO / ATTACK), or fire immediate orders
 * (HOLD / RTB / CANCEL).
 */
import { useState } from "react";
import { Navigation, Crosshair, Square, RotateCcw, X, Loader2, Zap } from "lucide-react";
import { clsx } from "clsx";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";
import type { Platform } from "@/types";

function BarValue({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center min-w-[44px]">
      <span className={clsx("font-mono text-sm font-bold tabular-nums", color ?? "text-surface-100")}>{value}</span>
      <span className="font-mono text-2xs text-surface-500 uppercase tracking-widest">{label}</span>
    </div>
  );
}

function MiniBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-16 bg-surface-700 rounded-full overflow-hidden">
      <div
        className={clsx("h-full rounded-full transition-all duration-500", color)}
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  );
}

export function CommandBar() {
  const {
    platforms,
    selectedPlatformId,
    selectPlatform,
    orderMode,
    setOrderMode,
    clearOrderMode,
    activeGame,
    pushAlert,
  } = useGameStore();

  const [loading, setLoading] = useState<string | null>(null);

  const platform: Platform | null = selectedPlatformId ? (platforms[selectedPlatformId] ?? null) : null;

  // Only show for friendly, non-destroyed platforms
  if (!platform || platform.faction !== "US" || platform.status === "DESTROYED" || platform.status === "RETIRED") {
    if (!orderMode.active) return null;
  }

  const gameId = activeGame?.id;

  const isMoving = orderMode.active && orderMode.platformId === platform?.id && orderMode.orderType === "MOVE_TO";
  const isAttacking = orderMode.active && orderMode.platformId === platform?.id && orderMode.orderType === "ATTACK";
  const isOtherActive = orderMode.active && orderMode.platformId !== platform?.id;

  const issueOrder = async (orderType: "HOLD" | "RTB" | "ABORT") => {
    if (!gameId || !platform) return;
    setLoading(orderType);
    try {
      await api.submitOrder(gameId, platform.id, { order_type: orderType });
      pushAlert({ level: "info", title: "Order sent", body: `${platform.designation} — ${orderType}` });
      if (orderType === "ABORT") selectPlatform(null);
    } catch (e) {
      pushAlert({ level: "warning", title: "Order failed", body: `Could not send ${orderType} to ${platform?.designation}` });
    } finally {
      setLoading(null);
    }
  };

  const activateMoveMode = () => {
    if (!platform) return;
    if (isMoving) { clearOrderMode(); return; }
    clearOrderMode();
    setOrderMode({ active: true, platformId: platform.id, orderType: "MOVE_TO" });
  };

  const activateAttackMode = () => {
    if (!platform) return;
    if (isAttacking) { clearOrderMode(); return; }
    clearOrderMode();
    setOrderMode({ active: true, platformId: platform.id, orderType: "ATTACK" });
  };

  const healthColor = (v: number) => v > 0.6 ? "bg-accent-green" : v > 0.3 ? "bg-accent-amber" : "bg-accent-red";
  const fuelColor   = (v: number) => v > 0.4 ? "bg-accent-blue"  : v > 0.2 ? "bg-accent-amber" : "bg-accent-red";

  const statusColor: Record<string, string> = {
    ACTIVE:     "text-accent-green",
    IN_TRANSIT: "text-accent-blue",
    DOCKED:     "text-surface-400",
    ENGAGED:    "text-accent-red",
    DAMAGED:    "text-accent-amber",
  };

  // If another platform is in active order mode, show just the cancel bar
  if (isOtherActive) {
    return (
      <div className="absolute bottom-0 left-0 right-0 z-30 bg-surface-950/95 border-t border-surface-700 flex items-center justify-center gap-3 px-4 py-2">
        <span className="text-xs font-mono text-accent-blue animate-pulse">
          {orderMode.orderType === "MOVE_TO" ? "Click destination on map…" : "Click enemy unit to attack…"}
        </span>
        <button
          onClick={clearOrderMode}
          className="flex items-center gap-1 px-3 py-1 rounded text-xs font-mono bg-surface-800 hover:bg-surface-700 text-surface-300 border border-surface-600"
        >
          <X className="w-3 h-3" /> Cancel (ESC)
        </button>
      </div>
    );
  }

  if (!platform) return null;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 bg-surface-950/95 backdrop-blur-sm border-t border-surface-700 flex items-center gap-4 px-4 py-2.5">

      {/* Unit identity */}
      <div className="shrink-0 min-w-[160px]">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-mono font-semibold text-surface-100 truncate max-w-[140px]">{platform.designation}</span>
          <span className={clsx("text-2xs font-mono uppercase", statusColor[platform.status] ?? "text-surface-400")}>
            {platform.status}
          </span>
        </div>
        <span className="text-2xs font-mono text-surface-500 block truncate max-w-[160px]">{platform.type_key}</span>
      </div>

      <div className="w-px h-8 bg-surface-700 shrink-0" />

      {/* Stats */}
      <div className="flex items-center gap-4 shrink-0">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5">
            <span className="text-2xs font-mono text-surface-500 w-8">HP</span>
            <MiniBar value={platform.health} color={healthColor(platform.health)} />
            <span className="text-2xs font-mono text-surface-300 w-8 text-right">{Math.round(platform.health * 100)}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-2xs font-mono text-surface-500 w-8">Fuel</span>
            <MiniBar value={platform.fuel_state} color={fuelColor(platform.fuel_state)} />
            <span className="text-2xs font-mono text-surface-300 w-8 text-right">{Math.round(platform.fuel_state * 100)}%</span>
          </div>
        </div>
        <BarValue
          label="Speed"
          value={platform.speed != null ? `${Math.round(platform.speed)}kts` : "—"}
          color="text-accent-blue"
        />
        <BarValue
          label="Heading"
          value={platform.heading != null ? `${Math.round(platform.heading)}°` : "—"}
        />
      </div>

      <div className="w-px h-8 bg-surface-700 shrink-0" />

      {/* Order mode status / action buttons */}
      {(isMoving || isAttacking) ? (
        <div className="flex items-center gap-3 flex-1">
          <div className={clsx(
            "flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-mono font-semibold animate-pulse",
            isAttacking
              ? "bg-accent-red/20 border-accent-red/50 text-accent-red"
              : "bg-accent-blue/20 border-accent-blue/50 text-accent-blue",
          )}>
            {isAttacking ? <Crosshair className="w-3.5 h-3.5" /> : <Navigation className="w-3.5 h-3.5" />}
            {isAttacking ? "Click an enemy to attack" : "Click the map to move"}
          </div>
          <button
            onClick={clearOrderMode}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-mono bg-surface-800 hover:bg-surface-700 text-surface-300 border border-surface-600 transition-colors"
          >
            <X className="w-3 h-3" /> Cancel (ESC)
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-1">
          {/* MOVE */}
          <button
            onClick={activateMoveMode}
            className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-mono font-medium bg-accent-blue hover:bg-accent-blue/80 text-white transition-colors"
          >
            <Navigation className="w-3.5 h-3.5" />
            Move
          </button>

          {/* ATTACK */}
          <button
            onClick={activateAttackMode}
            className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-mono font-medium bg-accent-red hover:bg-accent-red/80 text-white transition-colors"
          >
            <Crosshair className="w-3.5 h-3.5" />
            Attack
          </button>

          {/* HOLD */}
          <button
            onClick={() => issueOrder("HOLD")}
            disabled={loading !== null}
            className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-600 text-surface-200 transition-colors disabled:opacity-50"
          >
            {loading === "HOLD" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
            Hold
          </button>

          {/* RTB */}
          <button
            onClick={() => issueOrder("RTB")}
            disabled={loading !== null}
            className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-600 text-accent-amber transition-colors disabled:opacity-50"
          >
            {loading === "RTB" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
            RTB
          </button>

          {/* Cancel all orders */}
          <button
            onClick={() => issueOrder("ABORT")}
            disabled={loading !== null}
            className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-mono bg-surface-800 hover:bg-surface-700 border border-surface-600 text-accent-red/80 transition-colors disabled:opacity-50"
          >
            {loading === "ABORT" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Cancel Orders
          </button>
        </div>
      )}

      {/* Dismiss selection */}
      <button
        onClick={() => { selectPlatform(null); clearOrderMode(); }}
        className="ml-auto shrink-0 p-1.5 rounded text-surface-500 hover:text-surface-200 hover:bg-surface-800 transition-colors"
        title="Deselect unit"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
