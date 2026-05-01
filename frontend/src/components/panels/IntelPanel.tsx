import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { IntelTrack } from "@/types";
import { Eye, EyeOff, AlertTriangle } from "lucide-react";

const CONFIDENCE_COLOR = (c: number) => {
  if (c > 0.7) return "text-accent-red";
  if (c > 0.4) return "text-accent-amber";
  return "text-surface-400";
};

const TRACK_ICON: Record<string, typeof Eye> = {
  CONFIRMED: Eye,
  PROBABLE:  Eye,
  POSSIBLE:  EyeOff,
  GHOST:     AlertTriangle,
};

export function IntelPanel() {
  const { intelTracks } = useGameStore();

  const tracks = Object.values(intelTracks).sort((a, b) => b.confidence - a.confidence);
  const confirmed = tracks.filter((t) => t.track_type === "CONFIRMED").length;
  const probable = tracks.filter((t) => t.track_type === "PROBABLE").length;

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Intelligence</span>
        <span className="text-2xs font-mono text-surface-400">{tracks.length} tracks</span>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-px bg-surface-700 border-b border-surface-700">
        {[
          { label: "Confirmed", value: confirmed,                  color: "text-accent-red" },
          { label: "Probable",  value: probable,                   color: "text-accent-amber" },
          { label: "Possible",  value: tracks.length - confirmed - probable, color: "text-surface-400" },
        ].map((s) => (
          <div key={s.label} className="bg-surface-900 px-2 py-2 text-center">
            <div className={`stat-value text-sm ${s.color}`}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Track list */}
      <div className="flex-1 overflow-y-auto">
        {tracks.length === 0 && (
          <div className="px-3 py-8 text-center">
            <EyeOff className="w-6 h-6 mx-auto mb-2 text-surface-600" />
            <p className="text-xs font-mono text-surface-500">No tracks</p>
          </div>
        )}
        {tracks.map((t) => {
          const Icon = TRACK_ICON[t.track_type] ?? Eye;
          return (
            <div key={t.id} className="px-3 py-2 border-b border-surface-800 hover:bg-surface-800 transition-colors">
              <div className="flex items-center gap-2 mb-1">
                <Icon className={`w-3 h-3 shrink-0 ${CONFIDENCE_COLOR(t.confidence)}`} />
                <span className="text-xs font-mono text-surface-100 truncate">
                  {t.platform_type_estimate ?? `TRACK-${t.id.slice(0, 6).toUpperCase()}`}
                </span>
                <span className={`ml-auto text-2xs font-mono font-bold ${CONFIDENCE_COLOR(t.confidence)}`}>
                  {Math.round(t.confidence * 100)}%
                </span>
              </div>
              <div className="flex items-center gap-3 text-2xs font-mono text-surface-400">
                <span>{t.track_type}</span>
                <span>{t.source}</span>
                {t.estimated_speed && <span>{t.estimated_speed} kts</span>}
                {t.estimated_heading && <span>{t.estimated_heading}°</span>}
              </div>
              <div className="text-2xs font-mono text-surface-500 mt-0.5">
                [{t.last_position[1].toFixed(2)}°N, {t.last_position[0].toFixed(2)}°E] T+{t.last_updated_tick}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
