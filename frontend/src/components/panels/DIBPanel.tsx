import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HealthBar } from "@/components/ui/HealthBar";
import { Factory, Package, TrendingUp } from "lucide-react";

export function DIBPanel() {
  const { facilities } = useGameStore();

  const allFacilities = Object.values(facilities);
  const productionFacilities = allFacilities.filter((f) =>
    ["SHIPYARD", "AIRCRAFT_FACTORY", "MISSILE_PLANT", "MUNITIONS_DEPOT"].includes(f.facility_type)
  );

  const totalOrders = allFacilities.reduce(
    (sum, f) => sum + (f.production_queue as unknown[]).length,
    0
  );

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Industrial Base</span>
        <span className="text-2xs font-mono text-surface-400">{totalOrders} orders</span>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-px bg-surface-700 border-b border-surface-700">
        {[
          { label: "Facilities",  value: productionFacilities.length,  icon: <Factory className="w-3 h-3" /> },
          { label: "Prod Orders", value: totalOrders,                   icon: <Package className="w-3 h-3" /> },
        ].map((stat) => (
          <div key={stat.label} className="bg-surface-900 px-3 py-2 flex items-center gap-2">
            <span className="text-surface-400">{stat.icon}</span>
            <div>
              <div className="stat-value text-sm">{stat.value}</div>
              <div className="stat-label">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Facility list */}
      <div className="flex-1 overflow-y-auto">
        {productionFacilities.length === 0 && (
          <div className="px-3 py-8 text-center">
            <Factory className="w-6 h-6 mx-auto mb-2 text-surface-600" />
            <p className="text-xs font-mono text-surface-500">No production facilities</p>
            <p className="text-2xs font-mono text-surface-600 mt-1">Load a scenario to begin</p>
          </div>
        )}
        {productionFacilities.map((f) => {
          const queue = f.production_queue as Array<{
            platform_type_key: string;
            quantity: number;
            quantity_complete: number;
            ticks_elapsed: number;
            ticks_per_unit: number;
          }>;
          const activeOrder = queue[0];
          const progress = activeOrder
            ? activeOrder.ticks_per_unit > 0
              ? activeOrder.ticks_elapsed / activeOrder.ticks_per_unit
              : 0
            : 0;

          return (
            <div key={f.id} className="border-b border-surface-800">
              <div className="px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-surface-100 truncate">{f.name}</span>
                  <StatusBadge status={f.power_state} />
                </div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-2xs font-mono text-surface-400 uppercase">{f.facility_type}</span>
                  <span className="text-2xs font-mono text-surface-500">{f.production_slots} slot{f.production_slots > 1 ? "s" : ""}</span>
                </div>
                <HealthBar value={f.health} label="Cond" />
              </div>
              {activeOrder && (
                <div className="px-3 pb-2 space-y-1">
                  <div className="flex justify-between text-2xs font-mono">
                    <span className="text-surface-400">Producing:</span>
                    <span className="text-surface-200">{activeOrder.platform_type_key}</span>
                  </div>
                  <div className="flex justify-between text-2xs font-mono">
                    <span className="text-surface-400">Progress:</span>
                    <span className="text-surface-200">
                      {activeOrder.quantity_complete}/{activeOrder.quantity}
                    </span>
                  </div>
                  <HealthBar value={progress} label="Prog" />
                  {queue.length > 1 && (
                    <div className="text-2xs font-mono text-surface-500">
                      +{queue.length - 1} queued
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
