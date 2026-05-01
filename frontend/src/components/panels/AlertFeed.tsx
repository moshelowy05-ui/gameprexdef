import { useGameStore } from "@/store/gameStore";
import { X, AlertTriangle, Info, AlertCircle } from "lucide-react";
import { clsx } from "clsx";

const LEVEL_STYLES = {
  info:     { bg: "bg-accent-blue/10 border-accent-blue/30",  icon: <Info className="w-3 h-3 text-accent-blue" />,         text: "text-accent-blue" },
  warning:  { bg: "bg-accent-amber/10 border-accent-amber/30", icon: <AlertTriangle className="w-3 h-3 text-accent-amber" />, text: "text-accent-amber" },
  critical: { bg: "bg-accent-red/10 border-accent-red/30",    icon: <AlertCircle className="w-3 h-3 text-accent-red" />,   text: "text-accent-red" },
};

export function AlertFeed() {
  const { alerts, dismissAlert } = useGameStore();

  if (alerts.length === 0) return null;

  return (
    <div className="absolute top-12 right-3 z-50 w-72 space-y-1.5 pointer-events-none">
      {alerts.slice(0, 5).map((alert) => {
        const styles = LEVEL_STYLES[alert.level];
        return (
          <div
            key={alert.id}
            className={clsx(
              "panel border flex gap-2 p-2 pointer-events-auto",
              styles.bg
            )}
          >
            <div className="mt-0.5 shrink-0">{styles.icon}</div>
            <div className="flex-1 min-w-0">
              <div className={clsx("text-2xs font-mono font-semibold", styles.text)}>
                {alert.title}
              </div>
              <div className="text-2xs font-mono text-surface-300 mt-0.5 line-clamp-2">
                {alert.body}
              </div>
            </div>
            <button
              onClick={() => dismissAlert(alert.id)}
              className="shrink-0 text-surface-500 hover:text-surface-200 transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
