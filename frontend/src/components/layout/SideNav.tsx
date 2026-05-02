import { clsx } from "clsx";
import {
  Crosshair,
  LayoutGrid,
  Radar,
  Factory,
  Package,
  Map,
  ChevronRight,
  Satellite,
  Swords,
} from "lucide-react";
import { useGameStore } from "@/store/gameStore";

type Panel = "force" | "missions" | "combat" | "dib" | "intel" | "logistics" | null;

const NAV_ITEMS: { id: Panel; label: string; icon: React.ReactNode; shortcut: string }[] = [
  { id: "force",     label: "Force Structure",   icon: <LayoutGrid className="w-4 h-4" />,  shortcut: "F" },
  { id: "missions",  label: "Mission Planning",   icon: <Crosshair className="w-4 h-4" />,   shortcut: "M" },
  { id: "combat",    label: "Combat Log",         icon: <Swords className="w-4 h-4" />,       shortcut: "C" },
  { id: "dib",       label: "Industrial Base",    icon: <Factory className="w-4 h-4" />,      shortcut: "I" },
  { id: "intel",     label: "Intelligence",       icon: <Radar className="w-4 h-4" />,        shortcut: "N" },
  { id: "logistics", label: "Logistics",          icon: <Package className="w-4 h-4" />,      shortcut: "L" },
];

export function SideNav() {
  const { activePanel, setActivePanel } = useGameStore();

  return (
    <div className="w-12 bg-surface-900 border-r border-surface-700 flex flex-col items-center py-3 gap-1 shrink-0">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => setActivePanel(activePanel === item.id ? null : item.id)}
          title={`${item.label} [${item.shortcut}]`}
          className={clsx(
            "w-8 h-8 rounded flex items-center justify-center transition-colors",
            activePanel === item.id
              ? "bg-accent-blue/20 text-accent-blue"
              : "text-surface-500 hover:text-surface-200 hover:bg-surface-800"
          )}
        >
          {item.icon}
        </button>
      ))}

      <div className="flex-1" />

      <button
        title="Satellite / Space"
        className="w-8 h-8 rounded flex items-center justify-center text-surface-500 hover:text-surface-200 hover:bg-surface-800 transition-colors"
      >
        <Satellite className="w-4 h-4" />
      </button>
    </div>
  );
}
