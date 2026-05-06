import { useEffect, useRef } from "react";
import { useGameStore } from "@/store/gameStore";
import { X, AlertTriangle, Info, AlertCircle } from "lucide-react";
import { clsx } from "clsx";

const LEVEL_STYLES = {
  info:     { bg: "bg-accent-blue/10 border-accent-blue/30",   icon: <Info className="w-3 h-3 text-accent-blue" />,          text: "text-accent-blue" },
  warning:  { bg: "bg-accent-amber/10 border-accent-amber/30", icon: <AlertTriangle className="w-3 h-3 text-accent-amber" />, text: "text-accent-amber" },
  critical: { bg: "bg-accent-red/10 border-accent-red/30",     icon: <AlertCircle className="w-3 h-3 text-accent-red" />,    text: "text-accent-red" },
};

// Auto-dismiss after this many ms per level
const AUTO_DISMISS_MS: Record<string, number> = {
  info:     6_000,
  warning:  10_000,
  critical: 20_000,
};

function AlertItem({ alert }: { alert: { id: string; level: "info" | "warning" | "critical"; title: string; body: string } }) {
  const { dismissAlert } = useGameStore();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const delay = AUTO_DISMISS_MS[alert.level] ?? 8_000;
    timerRef.current = setTimeout(() => dismissAlert(alert.id), delay);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [alert.id, alert.level, dismissAlert]);

  const styles = LEVEL_STYLES[alert.level];

  return (
    <div
      className={clsx(
        "panel border flex gap-2 p-2 pointer-events-auto animate-in slide-in-from-right-4 duration-200",
        styles.bg,
      )}
    >
      <div className="mt-0.5 shrink-0">{styles.icon}</div>
      <div className="flex-1 min-w-0">
        <div className={clsx("text-2xs font-mono font-semibold", styles.text)}>
          {alert.title}
        </div>
        <div className="text-2xs font-mono text-surface-300 mt-0.5 line-clamp-3">
          {alert.body}
        </div>
      </div>
      <button
        onClick={() => dismissAlert(alert.id)}
        className="shrink-0 text-surface-500 hover:text-surface-200 transition-colors"
        title="Dismiss"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

export function AlertFeed() {
  const alerts = useGameStore((s) => s.alerts);

  if (alerts.length === 0) return null;

  return (
    <div className="absolute top-12 right-3 z-50 w-72 space-y-1.5 pointer-events-none">
      {alerts.slice(0, 6).map((alert) => (
        <AlertItem key={alert.id} alert={alert} />
      ))}
      {alerts.length > 6 && (
        <div className="text-2xs font-mono text-surface-500 text-right pr-1">
          +{alerts.length - 6} more
        </div>
      )}
    </div>
  );
}
