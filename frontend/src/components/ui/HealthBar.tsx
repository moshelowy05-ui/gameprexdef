import { clsx } from "clsx";

interface Props {
  value: number; // 0.0–1.0
  label?: string;
  className?: string;
}

export function HealthBar({ value, label, className }: Props) {
  const pct = Math.round(value * 100);
  const color =
    value > 0.6 ? "bg-accent-green" :
    value > 0.3 ? "bg-accent-amber" :
                  "bg-accent-red";

  return (
    <div className={clsx("flex items-center gap-2", className)}>
      {label && <span className="data-key w-12 shrink-0">{label}</span>}
      <div className="flex-1 h-1.5 bg-surface-700 rounded-full overflow-hidden">
        <div
          className={clsx("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="data-val w-8 text-right">{pct}%</span>
    </div>
  );
}
